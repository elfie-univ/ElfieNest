"""测试Owner REST API — 用户 CRUD / 精灵管理 / 配置读写

使用 tmp_path 隔离 DB，mock WS 网关避免端口冲突。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.persistence.store import get_db, init_db, verify_password
from app.interfaces.api.app import create_app

from ._helpers import create_test_owner, create_test_user

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "nest.db")


@pytest.fixture
def runtime_config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """临时 ELFIE_HOME/config.yaml 路径。"""
    p = tmp_path / "runtime" / "config.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ELFIE_HOME", str(p.parent))
    p.write_text("providers:\n  ollama:\n    api_base: http://localhost:11434\n")
    return p


@pytest.fixture
def app(db_path: str, runtime_config_path: Path):
    """创建 FastAPI 应用，mock WS 网关和 runtime_config 路径。"""
    # 预填充 owner 用户（ lifespan 不再硬编码 owner/ownerchangeme ）
    init_db(db_path)
    create_test_owner(db_path)

    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
        patch(
            "app.interfaces.api.owner_routes.get_config_path",
            return_value=runtime_config_path,
        ),
        patch(
            "app.interfaces.api.owner_user_routes.get_config_path",
            return_value=runtime_config_path,
        ),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        yield application


@pytest.fixture
def client(app):
    """FastAPI TestClient 实例。"""
    with TestClient(app) as c:
        yield c


def _login_owner(client: TestClient) -> dict:
    """辅助：以 owner 身份登录，返回 {"session_token", "csrf_token", "cookies"}。"""
    resp = client.post(
        "/api/auth/login", data={"username": "owner", "password": "ownerchangeme"}
    )
    assert resp.status_code == 200, f"login failed: {resp.text}"
    csrf_token = resp.headers.get("X-CSRF-Token", "")
    return {
        "csrf_token": csrf_token,
    }


def _headers(csrf_token: str) -> dict:
    """返回带 CSRF token 的请求头。"""
    return {"X-CSRF-Token": csrf_token, "Content-Type": "application/json"}


# ===================================================================
# 用户管理
# ===================================================================


class TestUserCRUD:
    def test_owner_cannot_update_owner_account(
        self, client: TestClient, db_path: str
    ) -> None:
        # Given
        tokens = _login_owner(client)
        owner_id = 1

        # When
        response = client.put(
            f"/api/owner/users/{owner_id}",
            json={"elfie_quota_override": 5},
            headers=_headers(tokens["csrf_token"]),
        )

        # Then
        assert response.status_code == 403
        with get_db(db_path) as conn:
            owner = conn.execute(
                "SELECT username, password_hash, role FROM users WHERE id = ?",
                (owner_id,),
            ).fetchone()
        assert owner["username"] == "owner"
        assert owner["role"] == "owner"
        assert verify_password("ownerchangeme", owner["password_hash"])

    def test_owner_role_cannot_be_demoted_via_user_update(
        self, client: TestClient, db_path: str
    ) -> None:
        # Given
        tokens = _login_owner(client)
        owner_id = 1

        # When
        response = client.put(
            f"/api/owner/users/{owner_id}",
            json={"role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )

        # Then
        assert response.status_code == 422
        with get_db(db_path) as conn:
            role = conn.execute(
                "SELECT role FROM users WHERE id = ?", (owner_id,)
            ).fetchone()["role"]
        assert role == "owner"

    def test_create_and_list(self, client: TestClient) -> None:
        """POST 创建 alice → GET 列表包含 alice。"""
        tokens = _login_owner(client)

        # 创建用户
        resp = client.post(
            "/api/owner/users",
            json={"username": "alice", "password": "pass123", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 201, resp.text
        user = resp.json()
        assert user["username"] == "alice"
        assert user["role"] == "user"
        assert "id" in user
        assert "password_hash" not in user  # 密码永不返回

        # 列表（owner 不会看到自己）
        resp = client.get("/api/owner/users", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 200
        usernames = [u["username"] for u in resp.json()]
        assert "alice" in usernames
        assert "owner" not in usernames  # 自己被过滤

    def test_duplicate_username_409(self, client: TestClient) -> None:
        """重复 username → 409。"""
        tokens = _login_owner(client)
        client.post(
            "/api/owner/users",
            json={"username": "alice", "password": "pass", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )
        resp = client.post(
            "/api/owner/users",
            json={"username": "alice", "password": "pass2", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 409

    def test_empty_username_422(self, client: TestClient) -> None:
        """空用户名 → 422。"""
        tokens = _login_owner(client)
        resp = client.post(
            "/api/owner/users",
            json={"username": "", "password": "pass", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_invalid_role_422(self, client: TestClient) -> None:
        """非法 role → 422。"""
        tokens = _login_owner(client)
        resp = client.post(
            "/api/owner/users",
            json={"username": "bob", "password": "pass", "role": "superowner"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_update_user_role(self, client: TestClient) -> None:
        """PUT 修改用户 role。"""
        tokens = _login_owner(client)
        resp = client.post(
            "/api/owner/users",
            json={"username": "alice", "password": "pass", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )
        user_id = resp.json()["id"]

        # 不允许再创建第二个Owner角色。
        resp = client.put(
            f"/api/owner/users/{user_id}",
            json={"role": "owner"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_user_list_projects_quota_and_unknown_online_state(
        self, client: TestClient
    ) -> None:
        tokens = _login_owner(client)
        client.post(
            "/api/owner/users",
            json={"username": "alice", "password": "pass", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )

        response = client.get(
            "/api/owner/users", headers=_headers(tokens["csrf_token"])
        )

        assert response.status_code == 200
        alice = next(user for user in response.json() if user["username"] == "alice")
        assert alice["elfie_quota_override"] is None
        assert alice["effective_elfie_limit"] == 3
        assert alice["online_status"] == "unknown"
        assert alice["avatar_url"] is None

    def test_update_user_only_accepts_quota_override(self, client: TestClient) -> None:
        tokens = _login_owner(client)
        created = client.post(
            "/api/owner/users",
            json={"username": "alice", "password": "pass", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        ).json()

        updated = client.put(
            f"/api/owner/users/{created['id']}",
            json={"elfie_quota_override": 6},
            headers=_headers(tokens["csrf_token"]),
        )
        forbidden = client.put(
            f"/api/owner/users/{created['id']}",
            json={"username": "renamed", "password": "new-pass", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )
        out_of_range = client.put(
            f"/api/owner/users/{created['id']}",
            json={"elfie_quota_override": 33},
            headers=_headers(tokens["csrf_token"]),
        )

        assert updated.status_code == 200
        assert updated.json()["elfie_quota_override"] == 6
        assert updated.json()["effective_elfie_limit"] == 6
        assert forbidden.status_code == 422
        assert out_of_range.status_code == 422

    def test_quota_override_can_return_to_system_default(
        self, client: TestClient
    ) -> None:
        tokens = _login_owner(client)
        created = client.post(
            "/api/owner/users",
            json={"username": "alice", "password": "pass", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        ).json()
        headers = _headers(tokens["csrf_token"])

        client.put(
            f"/api/owner/users/{created['id']}",
            json={"elfie_quota_override": 8},
            headers=headers,
        )
        response = client.put(
            f"/api/owner/users/{created['id']}",
            json={"elfie_quota_override": None},
            headers=headers,
        )

        assert response.status_code == 200
        assert response.json()["elfie_quota_override"] is None
        assert response.json()["effective_elfie_limit"] == 3

    def test_delete_user(self, client: TestClient) -> None:
        """删除用户 → 列表不再包含。"""
        tokens = _login_owner(client)
        resp = client.post(
            "/api/owner/users",
            json={"username": "alice", "password": "pass", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )
        user_id = resp.json()["id"]

        resp = client.delete(
            f"/api/owner/users/{user_id}",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200

        resp = client.get("/api/owner/users", headers=_headers(tokens["csrf_token"]))
        usernames = [u["username"] for u in resp.json()]
        assert "alice" not in usernames

    def test_cannot_delete_owner(self, client: TestClient) -> None:
        """不能从 Web 用户管理删除 Owner → 403。"""
        tokens = _login_owner(client)
        resp = client.delete(
            "/api/owner/users/1",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 403
        assert "Owner" in resp.text

    def test_delete_nonexistent_user_404(self, client: TestClient) -> None:
        """删除不存在的用户 → 404。"""
        tokens = _login_owner(client)
        resp = client.delete(
            "/api/owner/users/99999",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 404

    def test_delete_user_with_elfies_is_rejected(
        self, client: TestClient, db_path: str
    ) -> None:
        """删除用户前必须先转移或处理其名下精灵。"""
        tokens = _login_owner(client)
        # 创建用户 → 给用户分配一个精灵
        resp = client.post(
            "/api/owner/users",
            json={"username": "alice", "password": "pass", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )
        alice_id = resp.json()["id"]

        # 手动插入精灵
        from app.infrastructure.persistence.store import get_db

        with get_db(db_path) as conn:
            conn.execute(
                "INSERT INTO elfie_registry (elfie_id, name, owner_user_id) "
                "VALUES (?, ?, ?)",
                ("test_elfie", "测试精灵", alice_id),
            )
            conn.commit()

        # When
        response = client.delete(
            f"/api/owner/users/{alice_id}",
            headers=_headers(tokens["csrf_token"]),
        )

        # Then
        assert response.status_code == 409
        with get_db(db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM elfie_registry WHERE owner_user_id = ?",
                (alice_id,),
            )
            assert cursor.fetchone() is not None

    def test_owner_list_users_excludes_self(self, client: TestClient) -> None:
        """Owner列表不包含自己。"""
        tokens = _login_owner(client)
        resp = client.get("/api/owner/users", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 200

        usernames = [u["username"] for u in resp.json()]
        assert "owner" not in usernames

    def test_owner_list_users_shows_other_users(
        self, client: TestClient, db_path: str
    ) -> None:
        """Owner可以看到其他普通用户。"""
        tokens = _login_owner(client)

        create_test_user(db_path, "other_user", "pass", role="user")

        resp = client.get("/api/owner/users", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 200

        usernames = [u["username"] for u in resp.json()]
        assert "owner" not in usernames
        assert "other_user" in usernames


# ===================================================================
# 权限测试
# ===================================================================


class TestAuthorization:
    def test_non_owner_gets_403(self, client: TestClient) -> None:
        """普通用户访问 /api/owner/* → 403。"""
        tokens = _login_owner(client)

        # 创建普通用户
        resp = client.post(
            "/api/owner/users",
            json={"username": "alice", "password": "pass", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )

        # 以 alice 身份登录
        resp = client.post(
            "/api/auth/login", data={"username": "alice", "password": "pass"}
        )
        assert resp.status_code == 200
        alice_csrf = resp.headers.get("X-CSRF-Token", "")

        # 访问 owner 端点
        resp = client.get("/api/owner/users", headers=_headers(alice_csrf))
        assert resp.status_code == 403

        resp = client.get("/api/owner/config", headers=_headers(alice_csrf))
        assert resp.status_code == 403

    def test_unauthenticated_gets_401(self, client: TestClient) -> None:
        """未登录访问 → 401。"""
        resp = client.get("/api/owner/users")
        assert resp.status_code == 401

    def test_user_role_gets_403(self, client: TestClient, db_path: str) -> None:
        """普通用户登录后不能调用 Owner-only 管理接口。"""
        create_test_user(db_path, "normal_user", "pass", role="user")
        response = client.post(
            "/api/auth/login",
            data={"username": "normal_user", "password": "pass"},
        )
        assert response.status_code == 200
        csrf_token = response.headers.get("X-CSRF-Token", "")

        response = client.get("/api/owner/users", headers=_headers(csrf_token))

        assert response.status_code == 403
        assert "Owner" in response.text


# ===================================================================
# 精灵管理
# ===================================================================


class TestOwnerElfieList:
    def test_owner_elfies_list_available(
        self, client: TestClient, db_path: str
    ) -> None:
        tokens = _login_owner(client)
        headers = _headers(tokens["csrf_token"])

        with get_db(db_path) as conn:
            owner_id = conn.execute(
                "SELECT id FROM users WHERE username = ?",
                ("owner",),
            ).fetchone()["id"]
            room_cursor = conn.execute(
                "INSERT INTO rooms (name, max_capacity) VALUES (?, ?)",
                ("主精灵巢", 4),
            )
            room_id = room_cursor.lastrowid
            cursor = conn.execute(
                "INSERT INTO beds (room_id, name, grid_x, grid_y) VALUES (?, ?, ?, ?)",
                (room_id, "Bed 1", 0, 0),
            )
            bed_id = cursor.lastrowid
            conn.execute(
                "INSERT INTO elfie_registry "
                "(elfie_id, name, owner_user_id, anatomy_type, bed_id) "
                "VALUES (?, ?, ?, ?, ?)",
                ("elfie_001", "小白", owner_id, "biped", bed_id),
            )
            conn.commit()

        resp = client.get("/api/owner/elfies", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["elfie_id"] == "elfie_001"
        assert data[0]["profile"]["nest"]["bed_id"] == bed_id
        assert data[0]["profile"]["nest"]["room_name"] == "主精灵巢"
        assert data[0]["profile"]["appearance"] == {}
        assert "config_dir" not in data[0]

        resp = client.put(
            "/api/owner/elfies/test-id", json={"name": "test"}, headers=headers
        )
        assert resp.status_code == 404

        resp = client.delete("/api/owner/elfies/test-id", headers=headers)
        assert resp.status_code == 404


# ===================================================================
# LLM 配置管理
# ===================================================================


class TestConfig:
    def test_get_config(self, client: TestClient) -> None:
        """GET /api/owner/config → dict。"""
        tokens = _login_owner(client)
        resp = client.get("/api/owner/config", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert "providers" in data

    def test_put_config_valid(
        self, client: TestClient, runtime_config_path: Path
    ) -> None:
        """旧原始 PUT 已停用，配置文件保持不变。"""
        tokens = _login_owner(client)
        before = runtime_config_path.read_text(encoding="utf-8")
        new_config = {
            "providers": {
                "ollama": {"api_base": "http://127.0.0.1:11434"},
                "openai": {"api_key": "sk-test"},
            },
            "temperature": 0.7,
        }
        resp = client.put(
            "/api/owner/config",
            json=new_config,
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 410
        assert runtime_config_path.read_text(encoding="utf-8") == before

    def test_put_config_missing_providers_is_also_retired(
        self, client: TestClient
    ) -> None:
        """停用边界不因请求体形状而改变。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/owner/config",
            json={"temperature": 0.5},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 410

    def test_get_config_no_file(
        self, client: TestClient, runtime_config_path: Path
    ) -> None:
        """文件不存在时返回空 dict。"""
        runtime_config_path.unlink()  # 删除 mock 配置文件
        tokens = _login_owner(client)
        resp = client.get("/api/owner/config", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 200
        assert resp.json() == {}
