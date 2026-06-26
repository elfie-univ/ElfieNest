"""测试 Profile + 密码修改端点 — GET/PUT /api/auth/me/profile, POST /api/auth/me/password, GET /api/auth/me 扩展字段

使用 tmp_path 隔离 DB，mock WS 网关避免端口冲突。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from elfienest.api.app import create_app
from elfienest.persistence.store import get_db, init_db

from ._helpers import create_test_admin

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
    create_test_admin(db_path)

    with (
        patch("elfienest.api.app.AuthenticatedWSManager.start"),
        patch("elfienest.api.app.AuthenticatedWSManager.stop"),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        yield application


@pytest.fixture
def client(app):
    """FastAPI TestClient 实例。"""
    with TestClient(app) as c:
        yield c


def _login_admin(client: TestClient) -> dict:
    """辅助：以 admin 身份登录。"""
    resp = client.post(
        "/api/auth/login", data={"username": "admin", "password": "adminchangeme"}
    )
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
# GET /api/auth/me
# ===================================================================


class TestMe:
    def test_me_returns_full_schema(self, client: TestClient) -> None:
        """GET /api/auth/me 返回全部 9 字段。"""
        tokens = _login_admin(client)
        resp = client.get(
            "/api/auth/me",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert set(data.keys()) == {
            "id", "username", "role", "nickname",
            "avatar_color", "avatar_kind", "csrf_token",
            "created_at", "elfie_count", "session_token",
        }
        assert data["id"] == 1
        assert data["username"] == "admin"
        assert data["role"] == "admin"
        assert data["nickname"] is None
        assert data["avatar_color"] == 0
        assert data["avatar_kind"] == "initials"
        assert "csrf_token" in data
        assert "created_at" in data
        assert data["elfie_count"] == 0

    def test_me_returns_elfie_count(self, client: TestClient, db_path: str) -> None:
        """elfie_count 反映用户拥有的精灵数量。"""
        tokens = _login_admin(client)

        # 插入两个精灵给 admin
        with get_db(db_path) as conn:
            conn.execute(
                "INSERT INTO elfie_registry (elfie_id, name, owner_user_id) "
                "VALUES (?, ?, (SELECT id FROM users WHERE username='admin'))",
                ("e1", "精灵一"),
            )
            conn.execute(
                "INSERT INTO elfie_registry (elfie_id, name, owner_user_id) "
                "VALUES (?, ?, (SELECT id FROM users WHERE username='admin'))",
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
        tokens = _login_admin(client)
        resp = client.get(
            "/api/auth/me/profile",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert set(data.keys()) == {"username", "nickname", "avatar_color", "avatar_kind"}
        assert data["username"] == "admin"
        assert data["nickname"] is None
        assert data["avatar_color"] == 0
        assert data["avatar_kind"] == "initials"


# ===================================================================
# PUT /api/auth/me/profile
# ===================================================================


class TestUpdateProfile:
    def test_update_profile_nickname(self, client: TestClient) -> None:
        """PUT 更新 nickname 成功。"""
        tokens = _login_admin(client)
        resp = client.put(
            "/api/auth/me/profile",
            json={"nickname": "管理员"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["nickname"] == "管理员"
        assert data["username"] == "admin"

        # 验证持久化
        resp2 = client.get(
            "/api/auth/me/profile",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp2.json()["nickname"] == "管理员"

    def test_update_profile_avatar_color(self, client: TestClient) -> None:
        """PUT 更新 avatar_color 成功。"""
        tokens = _login_admin(client)
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
        tokens = _login_admin(client)
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
        tokens = _login_admin(client)

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
        tokens = _login_admin(client)
        resp = client.put(
            "/api/auth/me/profile",
            json={"avatar_kind": "invalid"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_update_profile_nickname_too_long(self, client: TestClient) -> None:
        """nickname 超过 32 字符返回 422。"""
        tokens = _login_admin(client)
        resp = client.put(
            "/api/auth/me/profile",
            json={"nickname": "a" * 33},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_update_profile_empty_body_400(self, client: TestClient) -> None:
        """空请求体（无任何字段）返回 400。"""
        tokens = _login_admin(client)
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
        tokens = _login_admin(client)
        resp = client.post(
            "/api/auth/me/password",
            json={"old_password": "adminchangeme", "new_password": "newpass123"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["detail"] == "密码已更新"

        # 验证可以用新密码登录
        resp = client.post(
            "/api/auth/login",
            data={"username": "admin", "password": "newpass123"},
        )
        assert resp.status_code == 200

        # 验证旧密码不再可用
        resp = client.post(
            "/api/auth/login",
            data={"username": "admin", "password": "adminchangeme"},
        )
        assert resp.status_code == 401

    def test_change_password_wrong_old(self, client: TestClient) -> None:
        """旧密码错误返回 400。"""
        tokens = _login_admin(client)
        resp = client.post(
            "/api/auth/me/password",
            json={"old_password": "wrongpass", "new_password": "newpass123"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 400
        assert "旧密码错误" in resp.text

    def test_change_password_same_as_old(self, client: TestClient) -> None:
        """新旧密码相同返回 400。"""
        tokens = _login_admin(client)
        resp = client.post(
            "/api/auth/me/password",
            json={"old_password": "adminchangeme", "new_password": "adminchangeme"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 400
        assert "新密码不能与旧密码相同" in resp.text

    def test_change_password_too_short(self, client: TestClient) -> None:
        """新密码少于 6 字符返回 422。"""
        tokens = _login_admin(client)

        # 5 字符
        resp = client.post(
            "/api/auth/me/password",
            json={"old_password": "adminchangeme", "new_password": "12345"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

        # 空字符串
        resp = client.post(
            "/api/auth/me/password",
            json={"old_password": "adminchangeme", "new_password": ""},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422
