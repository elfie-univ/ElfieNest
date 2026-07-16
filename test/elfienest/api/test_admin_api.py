"""测试管理员 REST API — 用户 CRUD / 精灵管理 / 配置读写

使用 tmp_path 隔离 DB，mock WS 网关避免端口冲突。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from elfienest.api.app import create_app
from elfienest.persistence.store import get_db, init_db, verify_password

from ._helpers import create_test_admin, create_test_user

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "nest.db")


@pytest.fixture
def runtime_config_path(tmp_path: Path) -> Path:
    """临时 runtime_config.json 路径，用于 mock admin_routes._RUNTIME_CONFIG_PATH。"""
    p = tmp_path / "runtime" / "runtime_config.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"providers": {"ollama": {"api_base": "http://localhost:11434"}}}')
    return p


@pytest.fixture
def app(db_path: str, runtime_config_path: Path):
    """创建 FastAPI 应用，mock WS 网关和 runtime_config 路径。"""
    # 预填充 admin 用户（ lifespan 不再硬编码 admin/adminchangeme ）
    init_db(db_path)
    create_test_admin(db_path)

    with (
        patch("elfienest.api.app.AuthenticatedWSManager.start"),
        patch("elfienest.api.app.AuthenticatedWSManager.stop"),
        patch("elfienest.api.admin_routes._RUNTIME_CONFIG_PATH", runtime_config_path),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        yield application


@pytest.fixture
def client(app):
    """FastAPI TestClient 实例。"""
    with TestClient(app) as c:
        yield c


def _login_admin(client: TestClient) -> dict:
    """辅助：以 admin 身份登录，返回 {"session_token", "csrf_token", "cookies"}。"""
    resp = client.post("/api/auth/login", data={"username": "admin", "password": "adminchangeme"})
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
    def test_admin_cannot_update_owner_account(self, client: TestClient, db_path: str) -> None:
        # Given
        tokens = _login_admin(client)
        owner_id = 1

        # When
        response = client.put(
            f"/api/admin/users/{owner_id}",
            json={"username": "attacker", "password": "attacker-password"},
            headers=_headers(tokens["csrf_token"]),
        )

        # Then
        assert response.status_code == 403
        with get_db(db_path) as conn:
            owner = conn.execute(
                "SELECT username, password_hash, role FROM users WHERE id = ?",
                (owner_id,),
            ).fetchone()
        assert owner["username"] == "admin"
        assert owner["role"] == "owner"
        assert verify_password("adminchangeme", owner["password_hash"])

    def test_owner_role_cannot_be_demoted_via_user_update(
        self, client: TestClient, db_path: str
    ) -> None:
        # Given
        tokens = _login_admin(client)
        owner_id = 1

        # When
        response = client.put(
            f"/api/admin/users/{owner_id}",
            json={"role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )

        # Then
        assert response.status_code == 403
        with get_db(db_path) as conn:
            role = conn.execute(
                "SELECT role FROM users WHERE id = ?", (owner_id,)
            ).fetchone()["role"]
        assert role == "owner"

    def test_create_and_list(self, client: TestClient) -> None:
        """POST 创建 alice → GET 列表包含 alice。"""
        tokens = _login_admin(client)

        # 创建用户
        resp = client.post(
            "/api/admin/users",
            json={"username": "alice", "password": "pass123", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 201, resp.text
        user = resp.json()
        assert user["username"] == "alice"
        assert user["role"] == "user"
        assert "id" in user
        assert "password_hash" not in user  # 密码永不返回

        # 列表（admin 不会看到自己）
        resp = client.get("/api/admin/users", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 200
        usernames = [u["username"] for u in resp.json()]
        assert "alice" in usernames
        assert "admin" not in usernames  # 自己被过滤

    def test_duplicate_username_409(self, client: TestClient) -> None:
        """重复 username → 409。"""
        tokens = _login_admin(client)
        client.post(
            "/api/admin/users",
            json={"username": "alice", "password": "pass", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )
        resp = client.post(
            "/api/admin/users",
            json={"username": "alice", "password": "pass2", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 409

    def test_empty_username_422(self, client: TestClient) -> None:
        """空用户名 → 422。"""
        tokens = _login_admin(client)
        resp = client.post(
            "/api/admin/users",
            json={"username": "", "password": "pass", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_invalid_role_422(self, client: TestClient) -> None:
        """非法 role → 422。"""
        tokens = _login_admin(client)
        resp = client.post(
            "/api/admin/users",
            json={"username": "bob", "password": "pass", "role": "superadmin"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_update_user_role(self, client: TestClient) -> None:
        """PUT 修改用户 role。"""
        tokens = _login_admin(client)
        resp = client.post(
            "/api/admin/users",
            json={"username": "alice", "password": "pass", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )
        user_id = resp.json()["id"]

        # 不允许再创建第二个管理员角色。
        resp = client.put(
            f"/api/admin/users/{user_id}",
            json={"role": "admin"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_delete_user(self, client: TestClient) -> None:
        """删除用户 → 列表不再包含。"""
        tokens = _login_admin(client)
        resp = client.post(
            "/api/admin/users",
            json={"username": "alice", "password": "pass", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )
        user_id = resp.json()["id"]

        resp = client.delete(
            f"/api/admin/users/{user_id}",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200

        resp = client.get("/api/admin/users", headers=_headers(tokens["csrf_token"]))
        usernames = [u["username"] for u in resp.json()]
        assert "alice" not in usernames

    def test_cannot_delete_owner(self, client: TestClient) -> None:
        """不能从 Web 用户管理删除 Owner → 400。"""
        tokens = _login_admin(client)
        resp = client.delete(
            "/api/admin/users/1",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 400
        assert "Owner" in resp.text

    def test_delete_nonexistent_user_404(self, client: TestClient) -> None:
        """删除不存在的用户 → 404。"""
        tokens = _login_admin(client)
        resp = client.delete(
            "/api/admin/users/99999",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 404

    def test_delete_user_destroys_elfies(self, client: TestClient, db_path: str) -> None:
        """删除用户 → 级联删除其精灵（registry 记录）。"""
        tokens = _login_admin(client)
        # 创建用户 → 给用户分配一个精灵
        resp = client.post(
            "/api/admin/users",
            json={"username": "alice", "password": "pass", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )
        alice_id = resp.json()["id"]

        # 手动插入精灵
        from elfienest.persistence.store import get_db
        with get_db(db_path) as conn:
            conn.execute(
                "INSERT INTO elfie_registry (elfie_id, name, owner_user_id) "
                "VALUES (?, ?, ?)",
                ("test_elfie", "测试精灵", alice_id),
            )
            conn.commit()

        # 删除用户
        client.delete(
            f"/api/admin/users/{alice_id}",
            headers=_headers(tokens["csrf_token"]),
        )

        # 验证精灵已被完全删除（不再是 NULL，而是记录不存在）
        with get_db(db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM elfie_registry WHERE owner_user_id = ?",
                (alice_id,),
            )
            assert cursor.fetchone() is None

    def test_admin_list_users_excludes_self(self, client: TestClient) -> None:
        """管理员列表不包含自己。"""
        tokens = _login_admin(client)
        resp = client.get("/api/admin/users", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 200

        usernames = [u["username"] for u in resp.json()]
        assert "admin" not in usernames

    def test_admin_list_users_shows_other_admins(self, client: TestClient, db_path: str) -> None:
        """管理员可以看到其他管理员。"""
        tokens = _login_admin(client)
        from ._helpers import create_test_user

        create_test_user(db_path, "other_admin", "pass", role="admin")

        resp = client.get("/api/admin/users", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 200

        usernames = [u["username"] for u in resp.json()]
        assert "admin" not in usernames
        assert "other_admin" in usernames


# ===================================================================
# 权限测试
# ===================================================================


class TestAuthorization:
    def test_non_admin_gets_403(self, client: TestClient) -> None:
        """普通用户访问 /api/admin/* → 403。"""
        tokens = _login_admin(client)

        # 创建普通用户
        resp = client.post(
            "/api/admin/users",
            json={"username": "alice", "password": "pass", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )

        # 以 alice 身份登录
        resp = client.post("/api/auth/login", data={"username": "alice", "password": "pass"})
        assert resp.status_code == 200
        alice_csrf = resp.headers.get("X-CSRF-Token", "")

        # 访问 admin 端点
        resp = client.get("/api/admin/users", headers=_headers(alice_csrf))
        assert resp.status_code == 403

        resp = client.get("/api/admin/config", headers=_headers(alice_csrf))
        assert resp.status_code == 403

    def test_unauthenticated_gets_401(self, client: TestClient) -> None:
        """未登录访问 → 401。"""
        resp = client.get("/api/admin/users")
        assert resp.status_code == 401

    def test_legacy_admin_role_gets_403(self, client: TestClient, db_path: str) -> None:
        """旧 admin role 登录后不能调用 Owner-only 管理接口。"""
        create_test_user(db_path, "legacy_admin", "pass", role="admin")
        response = client.post(
            "/api/auth/login",
            data={"username": "legacy_admin", "password": "pass"},
        )
        assert response.status_code == 200
        csrf_token = response.headers.get("X-CSRF-Token", "")

        response = client.get("/api/admin/users", headers=_headers(csrf_token))

        assert response.status_code == 403
        assert "Owner" in response.text


# ===================================================================
# 精灵管理
# ===================================================================


class TestAdminElfieList:
    def test_admin_elfies_list_available(self, client: TestClient, db_path: str) -> None:
        tokens = _login_admin(client)
        headers = _headers(tokens["csrf_token"])

        with get_db(db_path) as conn:
            admin_id = conn.execute(
                "SELECT id FROM users WHERE username = ?",
                ("admin",),
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
                ("elfie_001", "小白", admin_id, "biped", bed_id),
            )
            conn.commit()

        resp = client.get("/api/admin/elfies", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["elfie_id"] == "elfie_001"
        assert data[0]["bed_id"] == bed_id
        assert data[0]["room_name"] == "主精灵巢"

        resp = client.put("/api/admin/elfies/test-id", json={"name": "test"}, headers=headers)
        assert resp.status_code == 404

        resp = client.delete("/api/admin/elfies/test-id", headers=headers)
        assert resp.status_code == 404


# ===================================================================
# LLM 配置管理
# ===================================================================


class TestConfig:
    def test_get_config(self, client: TestClient) -> None:
        """GET /api/admin/config → dict。"""
        tokens = _login_admin(client)
        resp = client.get("/api/admin/config", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert "providers" in data

    def test_put_config_valid(self, client: TestClient, runtime_config_path: Path) -> None:
        """PUT 写入正确配置。"""
        tokens = _login_admin(client)
        new_config = {
            "providers": {
                "ollama": {"api_base": "http://127.0.0.1:11434"},
                "openai": {"api_key": "sk-test"},
            },
            "temperature": 0.7,
        }
        resp = client.put(
            "/api/admin/config",
            json=new_config,
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200

        # 验证文件已写入
        written = json.loads(runtime_config_path.read_text())
        assert written["providers"]["ollama"]["api_base"] == "http://127.0.0.1:11434"
        assert written["temperature"] == 0.7

    def test_put_config_missing_providers_400(self, client: TestClient) -> None:
        """PUT 缺少 providers → 400。"""
        tokens = _login_admin(client)
        resp = client.put(
            "/api/admin/config",
            json={"temperature": 0.5},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 400
        assert "providers" in resp.text

    def test_get_config_no_file(self, client: TestClient, runtime_config_path: Path) -> None:
        """文件不存在时返回空 dict。"""
        runtime_config_path.unlink()  # 删除 mock 配置文件
        tokens = _login_admin(client)
        resp = client.get("/api/admin/config", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 200
        assert resp.json() == {}
