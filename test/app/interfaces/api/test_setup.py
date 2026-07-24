"""测试首启向导 — /api/auth/setup-status & /api/auth/setup

使用 tmp_path 隔离 DB，mock WS 网关。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.interfaces.api.app import create_app

from ._helpers import create_test_owner


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "nest.db")


@pytest.fixture
def app(db_path: str):
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        yield application


@pytest.fixture
def client(app):
    with TestClient(app, base_url="http://127.0.0.1:8000") as c:
        yield c


class TestSetupStatus:
    def test_setup_status_empty_db(self, client: TestClient) -> None:
        """空数据库时 GET /api/auth/setup-status 返回 need_setup=true。"""
        resp = client.get("/api/auth/setup-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"need_setup": True}

    def test_setup_status_with_users(self, client: TestClient, db_path: str) -> None:
        """有用户时返回 need_setup=false。"""
        create_test_owner(db_path)
        resp = client.get("/api/auth/setup-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"need_setup": False}


class TestSetup:
    def test_setup_creates_owner(self, client: TestClient) -> None:
        """POST /api/auth/setup 在无用户时成功创建 owner（201）。"""
        resp = client.post(
            "/api/auth/setup",
            json={"username": "owner", "password": "securePass123"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["username"] == "owner"
        assert data["role"] == "owner"
        assert "id" in data
        assert "csrf_token" in data

        # 验证 session cookie 已设置
        assert "session_token" in resp.cookies
        assert len(resp.cookies["session_token"]) == 64

        # 验证 X-CSRF-Token header
        assert "x-csrf-token" in resp.headers

    def test_setup_cookie_uses_configured_session_ttl(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """POST /api/auth/setup 的 cookie TTL 与统一 session TTL 保持一致。"""
        monkeypatch.setattr(
            "app.interfaces.api.setup_routes.get_session_ttl_seconds",
            lambda _db_path: 86400,
        )

        resp = client.post(
            "/api/auth/setup",
            json={"username": "owner", "password": "securePass123"},
        )

        assert resp.status_code == 201, resp.text
        assert "Max-Age=86400" in resp.headers["set-cookie"]

    def test_setup_blocked_when_users_exist(self, client: TestClient, db_path: str) -> None:
        """POST /api/auth/setup 在有用户时返回 409。"""
        create_test_owner(db_path)
        resp = client.post(
            "/api/auth/setup",
            json={"username": "another", "password": "securePass123"},
        )
        assert resp.status_code == 409
        assert "已有用户" in resp.text

    def test_setup_validates_username_length(self, client: TestClient) -> None:
        """用户名少于3字符返回 422。"""
        resp = client.post(
            "/api/auth/setup",
            json={"username": "ab", "password": "securePass123"},
        )
        assert resp.status_code == 422

    def test_setup_validates_password_length(self, client: TestClient) -> None:
        """密码少于6字符返回 422。"""
        resp = client.post(
            "/api/auth/setup",
            json={"username": "owner", "password": "short"},
        )
        assert resp.status_code == 422

    def test_setup_validates_avatar_color(self, client: TestClient) -> None:
        """avatar_color 超出 0-7 返回 422。"""
        resp = client.post(
            "/api/auth/setup",
            json={"username": "owner", "password": "securePass123", "avatar_color": 8},
        )
        assert resp.status_code == 422

        resp = client.post(
            "/api/auth/setup",
            json={"username": "owner", "password": "securePass123", "avatar_color": -1},
        )
        assert resp.status_code == 422
