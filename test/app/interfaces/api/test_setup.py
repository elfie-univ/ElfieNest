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
def app(db_path: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ELFIE_HOME", str(Path(db_path).parent))
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
        """空数据库时状态 API 从第一步开始，并公开五步进度。"""
        resp = client.get("/api/auth/setup-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["need_setup"] is True
        assert data["complete"] is False
        assert data["current_step"] == 1
        assert [step["number"] for step in data["steps"]] == [1, 2, 3, 4]
        assert data["steps"][0]["status"] == "current"

    def test_setup_status_with_users(self, client: TestClient, db_path: str) -> None:
        """已有 Owner 不是 Setup 完成：迁移后必须从第二步继续。"""
        create_test_owner(db_path)
        resp = client.get("/api/auth/setup-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["need_setup"] is True
        assert data["current_step"] == 2
        assert data["steps"][0]["status"] == "completed"


class TestSetup:
    def test_setup_rejects_legacy_username(self, client: TestClient) -> None:
        response = client.post(
            "/api/auth/setup",
            json={"username": "owner", "password": "securePass123"},
        )

        assert response.status_code == 422

    def test_setup_rejects_lan_client_before_owner_exists(
        self, app, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """首启只能从本机或 Electron 回环服务完成，LAN 不能抢注 Owner。"""
        monkeypatch.setattr(
            "app.interfaces.api.service_access.private_ipv4_addresses",
            lambda: ("192.168.1.8",),
        )
        lan_app = create_app(
            engine=None,
            db_path=app.state.db_path,
            ws_port=9877,
            service_mode="lan",
        )
        with TestClient(
            lan_app,
            base_url="http://192.168.1.8:8000",
            client=("192.168.1.30", 50000),
        ) as lan_client:
            response = lan_client.post(
                "/api/auth/setup",
                json={"account_id": "owner", "password": "securePass123"},
            )

        assert response.status_code == 403

    def test_setup_creates_owner(self, client: TestClient) -> None:
        """POST /api/auth/setup 在无用户时成功创建 owner（201）。"""
        resp = client.post(
            "/api/auth/setup",
            json={"account_id": "owner", "password": "securePass123"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["account_id"] == "owner"
        assert data["display_name"] is None
        assert data["role"] == "owner"
        assert isinstance(data["user_id"], int)
        assert "id" not in data
        assert "username" not in data
        assert "nickname" not in data
        assert "csrf_token" in data

        # 验证 session cookie 已设置
        assert "session_token" in resp.cookies
        assert len(resp.cookies["session_token"]) == 64

        # 验证 X-CSRF-Token header
        assert "x-csrf-token" in resp.headers

        status = client.get("/api/auth/setup-status")
        assert status.status_code == 200
        assert status.json()["current_step"] == 2

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
            json={"account_id": "owner", "password": "securePass123"},
        )

        assert resp.status_code == 201, resp.text
        assert "Max-Age=86400" in resp.headers["set-cookie"]

    def test_setup_blocked_when_users_exist(
        self, client: TestClient, db_path: str
    ) -> None:
        """POST /api/auth/setup 在有用户时返回 409。"""
        create_test_owner(db_path)
        resp = client.post(
            "/api/auth/setup",
            json={"account_id": "another", "password": "securePass123"},
        )
        assert resp.status_code == 409
        assert "已有用户" in resp.text

    def test_setup_validates_account_id_length(self, client: TestClient) -> None:
        """登录账号少于3字符返回 422。"""
        resp = client.post(
            "/api/auth/setup",
            json={"account_id": "ab", "password": "securePass123"},
        )
        assert resp.status_code == 422

    def test_setup_validates_password_length(self, client: TestClient) -> None:
        """密码少于6字符返回 422。"""
        resp = client.post(
            "/api/auth/setup",
            json={"account_id": "owner", "password": "short"},
        )
        assert resp.status_code == 422

    def test_setup_validates_avatar_color(self, client: TestClient) -> None:
        """avatar_color 超出 0-7 返回 422。"""
        resp = client.post(
            "/api/auth/setup",
            json={
                "account_id": "owner",
                "password": "securePass123",
                "avatar_color": 8,
            },
        )
        assert resp.status_code == 422
