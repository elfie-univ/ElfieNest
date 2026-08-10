"""测试Owner REST API — 用户 CRUD / 精灵管理 / 配置读写

使用 tmp_path 隔离 DB，mock WS 网关避免端口冲突。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import create_app
from infrastructure.persistence.store import get_db, init_db, verify_password

from ._helpers import create_test_owner, create_test_user

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "nest.db")


@pytest.fixture
def app(db_path: str):
    """创建 FastAPI 应用并 mock WS 网关。"""
    # 预填充 owner 用户（ lifespan 不再硬编码 owner/ownerchangeme ）
    init_db(db_path)
    create_test_owner(db_path)

    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
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
        "/api/v1/auth/login", data={"account_id": "owner", "password": "ownerchangeme"}
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
        response = client.patch(
            f"/api/v1/admin/users/{owner_id}",
            json={"elfie_quota_override": 5},
            headers=_headers(tokens["csrf_token"]),
        )

        # Then
        assert response.status_code == 403
        with get_db(db_path) as conn:
            owner = conn.execute(
                "SELECT account_id, password_hash, role FROM users WHERE id = ?",
                (owner_id,),
            ).fetchone()
        assert owner["account_id"] == "owner"
        assert owner["role"] == "owner"
        assert verify_password("ownerchangeme", owner["password_hash"])

    def test_owner_role_cannot_be_demoted_via_user_update(
        self, client: TestClient, db_path: str
    ) -> None:
        # Given
        tokens = _login_owner(client)
        owner_id = 1

        # When
        response = client.patch(
            f"/api/v1/admin/users/{owner_id}",
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
            "/api/v1/admin/users",
            json={"account_id": "alice", "password": "pass123", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 201, resp.text
        user = resp.json()
        assert user["account_id"] == "alice"
        assert user["role"] == "user"
        assert isinstance(user["user_id"], int)
        assert "password_hash" not in user  # 密码永不返回

        # 列表包含只读 Owner。
        resp = client.get("/api/v1/admin/users", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 200
        account_ids = [u["account_id"] for u in resp.json()["items"]]
        assert "alice" in account_ids
        assert "owner" in account_ids

    def test_duplicate_account_id_409(self, client: TestClient) -> None:
        """重复 account_id → 409。"""
        tokens = _login_owner(client)
        client.post(
            "/api/v1/admin/users",
            json={"account_id": "alice", "password": "pass123", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )
        resp = client.post(
            "/api/v1/admin/users",
            json={"account_id": "alice", "password": "pass234", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 409

    def test_empty_account_id_422(self, client: TestClient) -> None:
        """空登录账号 → 422。"""
        tokens = _login_owner(client)
        resp = client.post(
            "/api/v1/admin/users",
            json={"account_id": "", "password": "pass123", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_invalid_role_422(self, client: TestClient) -> None:
        """非法 role → 422。"""
        tokens = _login_owner(client)
        resp = client.post(
            "/api/v1/admin/users",
            json={"account_id": "bob", "password": "pass123", "role": "superowner"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_user_role_update_route_is_removed(self, client: TestClient) -> None:
        """账号角色不提供 HTTP 升降级入口。"""
        tokens = _login_owner(client)
        resp = client.post(
            "/api/v1/admin/users",
            json={"account_id": "alice", "password": "pass123", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )
        user_id = resp.json()["user_id"]

        resp = client.patch(
            f"/api/v1/admin/users/{user_id}",
            json={"role": "owner"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_user_list_projects_quota_and_unknown_online_state(
        self, client: TestClient
    ) -> None:
        tokens = _login_owner(client)
        client.post(
            "/api/v1/admin/users",
            json={"account_id": "alice", "password": "pass123", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )

        response = client.get(
            "/api/v1/admin/users", headers=_headers(tokens["csrf_token"])
        )

        assert response.status_code == 200
        alice = next(
            user for user in response.json()["items"] if user["account_id"] == "alice"
        )
        assert alice["elfie_quota_override"] is None
        assert alice["effective_elfie_limit"] == 3
        assert alice["presence"] == "offline"
        assert alice["avatar_url"] is None

    def test_member_profile_update_route_is_removed(self, client: TestClient) -> None:
        tokens = _login_owner(client)
        created = client.post(
            "/api/v1/admin/users",
            json={"account_id": "alice", "password": "pass123", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        ).json()

        response = client.patch(
            f"/api/v1/admin/users/{created['user_id']}",
            json={"account_id": "renamed", "password": "new-pass123", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )

        assert response.status_code == 422

    def test_update_user_only_accepts_quota_override(self, client: TestClient) -> None:
        tokens = _login_owner(client)
        created = client.post(
            "/api/v1/admin/users",
            json={"account_id": "alice", "password": "pass123", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        ).json()
        headers = _headers(tokens["csrf_token"])

        updated = client.patch(
            f"/api/v1/admin/users/{created['user_id']}",
            json={"elfie_quota_override": 8},
            headers=headers,
        )
        forbidden = client.patch(
            f"/api/v1/admin/users/{created['user_id']}",
            json={"account_id": "renamed", "password": "new-pass123", "role": "user"},
            headers=headers,
        )
        out_of_range = client.patch(
            f"/api/v1/admin/users/{created['user_id']}",
            json={"elfie_quota_override": 33},
            headers=headers,
        )

        assert updated.status_code == 200
        assert updated.json()["elfie_quota_override"] == 8
        assert updated.json()["effective_elfie_limit"] == 8
        assert forbidden.status_code == 422
        assert out_of_range.status_code == 422

    def test_quota_override_can_return_to_system_default(
        self, client: TestClient
    ) -> None:
        tokens = _login_owner(client)
        created = client.post(
            "/api/v1/admin/users",
            json={"account_id": "alice", "password": "pass123", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        ).json()
        headers = _headers(tokens["csrf_token"])

        client.patch(
            f"/api/v1/admin/users/{created['user_id']}",
            json={"elfie_quota_override": 8},
            headers=headers,
        )
        response = client.patch(
            f"/api/v1/admin/users/{created['user_id']}",
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
            "/api/v1/admin/users",
            json={"account_id": "alice", "password": "pass123", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )
        user_id = resp.json()["user_id"]

        resp = client.delete(
            f"/api/v1/admin/users/{user_id}",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 204

        resp = client.get("/api/v1/admin/users", headers=_headers(tokens["csrf_token"]))
        account_ids = [u["account_id"] for u in resp.json()["items"]]
        assert "alice" not in account_ids

    def test_cannot_delete_owner(self, client: TestClient) -> None:
        """不能从 Web 用户管理删除 Owner → 403。"""
        tokens = _login_owner(client)
        resp = client.delete(
            "/api/v1/admin/users/1",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 403
        assert "只能管理低于当前角色" in resp.text

    def test_delete_nonexistent_user_404(self, client: TestClient) -> None:
        """删除不存在的用户 → 404。"""
        tokens = _login_owner(client)
        resp = client.delete(
            "/api/v1/admin/users/99999",
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
            "/api/v1/admin/users",
            json={"account_id": "alice", "password": "pass123", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )
        alice_id = resp.json()["user_id"]

        # 手动插入精灵
        from infrastructure.persistence.store import get_db

        with get_db(db_path) as conn:
            conn.execute(
                """INSERT INTO elfies
                   (elfie_id,name,owner_user_id,species,adopted_at,status)
                   VALUES (?,?,?,?,?,'offline')""",
                ("00000001", "测试精灵", alice_id, "fox", "2026-07-30T00:00:00Z"),
            )
            conn.commit()

        # When
        response = client.delete(
            f"/api/v1/admin/users/{alice_id}",
            headers=_headers(tokens["csrf_token"]),
        )

        # Then
        assert response.status_code == 409
        with get_db(db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM elfies WHERE owner_user_id = ?",
                (alice_id,),
            )
            assert cursor.fetchone() is not None

    def test_owner_list_users_includes_read_only_self(self, client: TestClient) -> None:
        """Owner list includes its read-only Owner row."""
        tokens = _login_owner(client)
        resp = client.get("/api/v1/admin/users", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 200

        account_ids = [u["account_id"] for u in resp.json()["items"]]
        assert "owner" in account_ids

    def test_owner_list_users_shows_other_users(
        self, client: TestClient, db_path: str
    ) -> None:
        """Owner可以看到其他普通用户。"""
        tokens = _login_owner(client)

        create_test_user(db_path, "other_user", "pass", role="user")

        resp = client.get("/api/v1/admin/users", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 200

        account_ids = [u["account_id"] for u in resp.json()["items"]]
        assert "owner" in account_ids
        assert "other_user" in account_ids


# ===================================================================
# 权限测试
# ===================================================================


class TestAuthorization:
    def test_non_owner_gets_403(self, client: TestClient) -> None:
        """普通用户访问 /api/owner/* → 403。"""
        tokens = _login_owner(client)

        # 创建普通用户
        resp = client.post(
            "/api/v1/admin/users",
            json={"account_id": "alice", "password": "pass123", "role": "user"},
            headers=_headers(tokens["csrf_token"]),
        )

        # 以 alice 身份登录
        resp = client.post(
            "/api/v1/auth/login", data={"account_id": "alice", "password": "pass123"}
        )
        assert resp.status_code == 200
        alice_csrf = resp.headers.get("X-CSRF-Token", "")

        # 访问 owner 端点
        resp = client.get("/api/v1/admin/users", headers=_headers(alice_csrf))
        assert resp.status_code == 403

    def test_unauthenticated_gets_401(self, client: TestClient) -> None:
        """未登录访问 → 401。"""
        resp = client.get("/api/v1/admin/users")
        assert resp.status_code == 401

    def test_user_role_gets_403(self, client: TestClient, db_path: str) -> None:
        """普通用户登录后不能调用 Owner-only 管理接口。"""
        create_test_user(db_path, "normal_user", "pass123", role="user")
        response = client.post(
            "/api/v1/auth/login",
            data={"account_id": "normal_user", "password": "pass123"},
        )
        assert response.status_code == 200
        csrf_token = response.headers.get("X-CSRF-Token", "")

        response = client.get("/api/v1/admin/users", headers=_headers(csrf_token))

        assert response.status_code == 403
        assert "Owner" in response.text
