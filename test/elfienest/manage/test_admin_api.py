"""测试管理员 REST API — 用户 CRUD / 精灵管理 / 配置读写

使用 tmp_path 隔离 DB，mock WS 网关避免端口冲突。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from elfienest.manage.app import create_app

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
    with (
        patch("elfienest.manage.app.AuthenticatedWSManager.start"),
        patch("elfienest.manage.app.AuthenticatedWSManager.stop"),
        patch("elfienest.manage.admin_routes._RUNTIME_CONFIG_PATH", runtime_config_path),
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
    data = resp.json()
    csrf_token = resp.headers.get("X-CSRF-Token", "")
    return {
        "session_token": data["session_token"],
        "csrf_token": csrf_token,
    }


def _headers(csrf_token: str) -> dict:
    """返回带 CSRF token 的请求头。"""
    return {"X-CSRF-Token": csrf_token, "Content-Type": "application/json"}


# ===================================================================
# 用户管理
# ===================================================================


class TestUserCRUD:
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

        # 列表
        resp = client.get("/api/admin/users", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 200
        usernames = [u["username"] for u in resp.json()]
        assert "alice" in usernames
        assert "admin" in usernames

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

        # 改 role 为 admin
        resp = client.put(
            f"/api/admin/users/{user_id}",
            json={"role": "admin"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"

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

    def test_cannot_delete_last_admin(self, client: TestClient) -> None:
        """不能删除唯一 admin → 400。"""
        tokens = _login_admin(client)
        resp = client.get("/api/admin/users", headers=_headers(tokens["csrf_token"]))
        users = resp.json()
        admin_ids = [u["id"] for u in users if u["role"] == "admin"]
        assert len(admin_ids) == 1

        resp = client.delete(
            f"/api/admin/users/{admin_ids[0]}",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 400
        assert "唯一的管理员" in resp.text

    def test_delete_nonexistent_user_404(self, client: TestClient) -> None:
        """删除不存在的用户 → 404。"""
        tokens = _login_admin(client)
        resp = client.delete(
            "/api/admin/users/99999",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 404

    def test_delete_user_cascades_elfie_owner(self, client: TestClient, db_path: str) -> None:
        """删除用户 → 级联清空精灵 owner。"""
        tokens = _login_admin(client)
        # 创建用户 → 给用户分配一个精灵
        resp = client.post(
            "/api/admin/users",
            json={"username": "alice", "password": "pass", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )
        alice_id = resp.json()["id"]

        # 手动插入精灵（admin API 不提供创建精灵）
        from elfienest.manage.store import get_db
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

        # 验证精灵 owner 被置空
        with get_db(db_path) as conn:
            row = conn.execute(
                "SELECT owner_user_id FROM elfie_registry WHERE elfie_id='test_elfie'"
            ).fetchone()
        assert row is None or row[0] is None


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

        resp = client.get("/api/admin/elfies", headers=_headers(alice_csrf))
        assert resp.status_code == 403

        resp = client.get("/api/admin/config", headers=_headers(alice_csrf))
        assert resp.status_code == 403

    def test_unauthenticated_gets_401(self, client: TestClient) -> None:
        """未登录访问 → 401。"""
        resp = client.get("/api/admin/users")
        assert resp.status_code == 401


# ===================================================================
# 精灵管理
# ===================================================================


class TestElfieManagement:
    def test_list_elfies_empty(self, client: TestClient) -> None:
        """GET /api/admin/elfies 返回空列表。"""
        tokens = _login_admin(client)
        resp = client.get("/api/admin/elfies", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_elfies_with_data(self, client: TestClient, db_path: str) -> None:
        """GET /api/admin/elfies 返回精灵数据。"""
        tokens = _login_admin(client)
        from elfienest.manage.store import get_db
        with get_db(db_path) as conn:
            conn.execute(
                "INSERT INTO elfie_registry "
                "(elfie_id, name, owner_user_id, anatomy_type, personality_style, height, build) "
                "VALUES (?, ?, (SELECT id FROM users WHERE username='admin'), ?, ?, ?, ?)",
                ("e1", "小白", "biped", "好奇探索", "tall", "slim"),
            )
            conn.commit()

        resp = client.get("/api/admin/elfies", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "小白"
        assert data[0]["anatomy_type"] == "biped"
        assert data[0]["personality_style"] == "好奇探索"
        assert data[0]["height"] == "tall"
        assert data[0]["build"] == "slim"

    def test_post_elfies_405(self, client: TestClient) -> None:
        """POST /api/admin/elfies → 405 Method Not Allowed。"""
        tokens = _login_admin(client)
        resp = client.post(
            "/api/admin/elfies",
            json={"name": "test"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 405

    def test_update_elfie_name(self, client: TestClient, db_path: str) -> None:
        """PUT 改精灵 name。"""
        tokens = _login_admin(client)
        from elfienest.manage.store import get_db
        with get_db(db_path) as conn:
            conn.execute(
                "INSERT INTO elfie_registry (elfie_id, name, owner_user_id) "
                "VALUES (?, ?, (SELECT id FROM users WHERE username='admin'))",
                ("e1", "小白"),
            )
            conn.commit()

        resp = client.put(
            "/api/admin/elfies/e1",
            json={"name": "大白"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "大白"

    def test_update_elfie_owner(self, client: TestClient, db_path: str) -> None:
        """PUT 改精灵 owner。"""
        tokens = _login_admin(client)
        from elfienest.manage.store import get_db
        with get_db(db_path) as conn:
            conn.execute(
                "INSERT INTO elfie_registry (elfie_id, name, owner_user_id) "
                "VALUES (?, ?, (SELECT id FROM users WHERE username='admin'))",
                ("e1", "小白"),
            )
            # 创建另一个用户
            from elfienest.manage.store import hash_password
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'user')",
                ("alice", hash_password("pass")),
            )
            conn.commit()

        resp = client.put(
            "/api/admin/elfies/e1",
            json={"owner_user_id": 2},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["owner_user_id"] == 2

    def test_update_elfie_anatomy_type_400(self, client: TestClient, db_path: str) -> None:
        """PUT 改 anatomy_type → 400（不可变）。"""
        tokens = _login_admin(client)
        from elfienest.manage.store import get_db
        with get_db(db_path) as conn:
            conn.execute(
                "INSERT INTO elfie_registry (elfie_id, name, owner_user_id) "
                "VALUES (?, ?, (SELECT id FROM users WHERE username='admin'))",
                ("e1", "小白"),
            )
            conn.commit()

        resp = client.put(
            "/api/admin/elfies/e1",
            json={"anatomy_type": "quadruped"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 400

    def test_delete_elfie(self, client: TestClient, db_path: str) -> None:
        """DELETE 精灵 → 从 registry 删除。"""
        tokens = _login_admin(client)
        from elfienest.manage.store import get_db
        with get_db(db_path) as conn:
            conn.execute(
                "INSERT INTO elfie_registry (elfie_id, name, owner_user_id) "
                "VALUES (?, ?, (SELECT id FROM users WHERE username='admin'))",
                ("e1", "小白"),
            )
            conn.commit()

        resp = client.delete(
            "/api/admin/elfies/e1",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200

        resp = client.get("/api/admin/elfies", headers=_headers(tokens["csrf_token"]))
        assert len(resp.json()) == 0

    def test_delete_nonexistent_elfie_404(self, client: TestClient) -> None:
        """删除不存在的精灵 → 404。"""
        tokens = _login_admin(client)
        resp = client.delete(
            "/api/admin/elfies/nonexistent",
            headers=_headers(tokens["csrf_token"]),
        )
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
