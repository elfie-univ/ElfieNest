"""测试 Profile + 密码修改端点 — GET/PUT /api/auth/me/profile, POST /api/auth/me/password, GET /api/auth/me 扩展字段

使用 tmp_path 隔离 DB，mock WS 网关避免端口冲突。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.persistence.store import get_db, init_db
from app.interfaces.api.app import create_app

from ._helpers import create_test_owner, create_test_user

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "nest.db")


@pytest.fixture
def app(db_path: str):
    """创建 FastAPI 应用，mock WS 网关。"""
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
    """辅助：以 owner 身份登录。"""
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
# GET /api/auth/me
# ===================================================================


class TestMe:
    def test_me_returns_full_schema(self, client: TestClient) -> None:
        """GET /api/auth/me 返回当前页面路由所需的全部字段。"""
        tokens = _login_owner(client)
        resp = client.get(
            "/api/auth/me",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert set(data.keys()) == {
            "id",
            "username",
            "role",
            "nickname",
            "avatar_color",
            "avatar_kind",
            "csrf_token",
            "created_at",
            "elfie_count",
            "default_landing_page",
            "theme_key",
        }
        assert "session_token" not in data
        assert data["id"] == 1
        assert data["username"] == "owner"
        assert data["role"] == "owner"
        assert data["nickname"] is None
        assert data["avatar_color"] == 0
        assert data["avatar_kind"] == "initials"
        assert data["default_landing_page"] == "manage"
        assert data["theme_key"] == "warm-paper"
        assert "csrf_token" in data
        assert "created_at" in data
        assert data["elfie_count"] == 0

    def test_me_returns_elfie_count(self, client: TestClient, db_path: str) -> None:
        """elfie_count 反映用户拥有的精灵数量。"""
        tokens = _login_owner(client)

        # 插入两个精灵给 owner
        with get_db(db_path) as conn:
            conn.execute(
                "INSERT INTO elfie_registry (elfie_id, name, owner_user_id) "
                "VALUES (?, ?, (SELECT id FROM users WHERE username='owner'))",
                ("e1", "精灵一"),
            )
            conn.execute(
                "INSERT INTO elfie_registry (elfie_id, name, owner_user_id) "
                "VALUES (?, ?, (SELECT id FROM users WHERE username='owner'))",
                ("e2", "精灵二"),
            )
            conn.commit()

        resp = client.get(
            "/api/auth/me",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["elfie_count"] == 2


# ===================================================================
# GET /api/auth/me/profile
# ===================================================================


class TestGetProfile:
    def test_get_profile(self, client: TestClient) -> None:
        """GET /api/auth/me/profile 返回 4 字段。"""
        tokens = _login_owner(client)
        resp = client.get(
            "/api/auth/me/profile",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert set(data.keys()) == {
            "username",
            "nickname",
            "avatar_color",
            "avatar_kind",
        }
        assert data["username"] == "owner"
        assert data["nickname"] is None
        assert data["avatar_color"] == 0
        assert data["avatar_kind"] == "initials"


# ===================================================================
# PUT /api/auth/me/theme
# ===================================================================


class TestThemePreference:
    def test_theme_preference_persists_for_the_authenticated_user(
        self, client: TestClient
    ) -> None:
        """当前登录用户可保存主题，且 ``/api/auth/me`` 返回持久化后的值。"""
        tokens = _login_owner(client)

        response = client.put(
            "/api/auth/me/theme",
            json={"theme_key": "harbor-blue"},
            headers=_headers(tokens["csrf_token"]),
        )

        assert response.status_code == 200
        assert response.json() == {"theme_key": "harbor-blue"}
        current = client.get("/api/auth/me", headers=_headers(tokens["csrf_token"]))
        assert current.json()["theme_key"] == "harbor-blue"

    def test_each_authenticated_user_keeps_their_own_theme(
        self, client: TestClient, db_path: str
    ) -> None:
        """Owner 与普通用户的主题偏好相互隔离。"""
        create_test_user(db_path, "member", "memberchangeme")
        owner_tokens = _login_owner(client)
        owner_update = client.put(
            "/api/auth/me/theme",
            json={"theme_key": "orchid-archive"},
            headers=_headers(owner_tokens["csrf_token"]),
        )
        assert owner_update.status_code == 200
        logout = client.post(
            "/api/auth/logout", headers={"X-CSRF-Token": owner_tokens["csrf_token"]}
        )
        assert logout.status_code == 200

        member_login = client.post(
            "/api/auth/login",
            data={"username": "member", "password": "memberchangeme"},
        )
        member_tokens = {"csrf_token": member_login.headers["X-CSRF-Token"]}
        member_update = client.put(
            "/api/auth/me/theme",
            json={"theme_key": "moss-green"},
            headers=_headers(member_tokens["csrf_token"]),
        )

        assert member_update.status_code == 200
        assert client.get("/api/auth/me", headers=_headers(member_tokens["csrf_token"])).json()[
            "theme_key"
        ] == "moss-green"
        with get_db(db_path) as conn:
            owner_theme = conn.execute(
                "SELECT theme_key FROM users WHERE username = 'owner'"
            ).fetchone()["theme_key"]
        assert owner_theme == "orchid-archive"

    def test_theme_preference_rejects_unknown_theme_key(
        self, client: TestClient
    ) -> None:
        """未注册主题不能写入用户偏好。"""
        tokens = _login_owner(client)

        response = client.put(
            "/api/auth/me/theme",
            json={"theme_key": "midnight"},
            headers=_headers(tokens["csrf_token"]),
        )

        assert response.status_code == 422
        current = client.get("/api/auth/me", headers=_headers(tokens["csrf_token"]))
        assert current.json()["theme_key"] == "warm-paper"


# ===================================================================
# PUT /api/auth/me/profile
# ===================================================================


class TestUpdateProfile:
    def test_update_profile_nickname(self, client: TestClient) -> None:
        """PUT 更新 nickname 成功。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/auth/me/profile",
            json={"nickname": "Owner"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["nickname"] == "Owner"
        assert data["username"] == "owner"

        # 验证持久化
        resp2 = client.get(
            "/api/auth/me/profile",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp2.json()["nickname"] == "Owner"

    def test_update_profile_avatar_color(self, client: TestClient) -> None:
        """PUT 更新 avatar_color 成功。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/auth/me/profile",
            json={"avatar_color": 3},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["avatar_color"] == 3
        assert data["avatar_kind"] == "initials"

        # 验证持久化
        resp2 = client.get(
            "/api/auth/me/profile",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp2.json()["avatar_color"] == 3

    def test_update_profile_avatar_kind(self, client: TestClient) -> None:
        """PUT 更新 avatar_kind 为 emoji。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/auth/me/profile",
            json={"avatar_kind": "emoji"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["avatar_kind"] == "emoji"

    def test_update_profile_avatar_color_out_of_range(self, client: TestClient) -> None:
        """avatar_color < 0 或 > 7 返回 422。"""
        tokens = _login_owner(client)

        # 超出上限
        resp = client.put(
            "/api/auth/me/profile",
            json={"avatar_color": 8},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

        # 低于下限
        resp = client.put(
            "/api/auth/me/profile",
            json={"avatar_color": -1},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_update_profile_avatar_kind_invalid(self, client: TestClient) -> None:
        """avatar_kind 为无效值返回 422。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/auth/me/profile",
            json={"avatar_kind": "invalid"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_update_profile_nickname_too_long(self, client: TestClient) -> None:
        """nickname 超过 32 字符返回 422。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/auth/me/profile",
            json={"nickname": "a" * 33},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_update_profile_empty_body_400(self, client: TestClient) -> None:
        """空请求体（无任何字段）返回 400。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/auth/me/profile",
            json={},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 400
        assert "没有提供要更新的字段" in resp.text


# ===================================================================
# POST /api/auth/me/password
# ===================================================================


class TestChangePassword:
    def test_change_password_success(self, client: TestClient) -> None:
        """POST 成功修改密码。"""
        tokens = _login_owner(client)
        resp = client.post(
            "/api/auth/me/password",
            json={"old_password": "ownerchangeme", "new_password": "newpass123"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["detail"] == "密码已更新"

        # 验证可以用新密码登录
        resp = client.post(
            "/api/auth/login",
            data={"username": "owner", "password": "newpass123"},
        )
        assert resp.status_code == 200

        # 验证旧密码不再可用
        resp = client.post(
            "/api/auth/login",
            data={"username": "owner", "password": "ownerchangeme"},
        )
        assert resp.status_code == 401

    def test_change_password_updates_account_timestamp(
        self, client: TestClient, db_path: str
    ) -> None:
        tokens = _login_owner(client)
        with get_db(db_path) as conn:
            conn.execute(
                "UPDATE users SET updated_at = 'old-timestamp' WHERE username = 'owner'"
            )
            conn.commit()

        response = client.post(
            "/api/auth/me/password",
            json={"old_password": "ownerchangeme", "new_password": "newpass123"},
            headers=_headers(tokens["csrf_token"]),
        )

        assert response.status_code == 200
        with get_db(db_path) as conn:
            updated_at = conn.execute(
                "SELECT updated_at FROM users WHERE username = 'owner'"
            ).fetchone()[0]
        assert updated_at != "old-timestamp"

    def test_change_password_wrong_old(self, client: TestClient) -> None:
        """旧密码错误返回 400。"""
        tokens = _login_owner(client)
        resp = client.post(
            "/api/auth/me/password",
            json={"old_password": "wrongpass", "new_password": "newpass123"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 400
        assert "旧密码错误" in resp.text

    def test_change_password_same_as_old(self, client: TestClient) -> None:
        """新旧密码相同返回 400。"""
        tokens = _login_owner(client)
        resp = client.post(
            "/api/auth/me/password",
            json={"old_password": "ownerchangeme", "new_password": "ownerchangeme"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 400
        assert "新密码不能与旧密码相同" in resp.text

    def test_change_password_too_short(self, client: TestClient) -> None:
        """新密码少于 6 字符返回 422。"""
        tokens = _login_owner(client)

        # 5 字符
        resp = client.post(
            "/api/auth/me/password",
            json={"old_password": "ownerchangeme", "new_password": "12345"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

        # 空字符串
        resp = client.post(
            "/api/auth/me/password",
            json={"old_password": "ownerchangeme", "new_password": ""},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422
