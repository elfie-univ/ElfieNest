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


class _QueuedOllamaJobs:
    """Avoid a real network/download while proving the HTTP request only queues work."""

    def __init__(self) -> None:
        self.started = False

    def start(self, *, db_path: str, worker):
        _ = db_path
        _ = worker
        self.started = True
        from app.features.setup.progress import SetupTask

        return SetupTask(
            step=2,
            key="ollama_install",
            state="running",
            progress=1,
            error=None,
        )

    def start_model_pull(self, *, db_path: str, worker):
        _ = db_path
        _ = worker
        self.started = True
        from app.features.setup.progress import SetupTask

        return SetupTask(
            step=4,
            key="model_pull",
            state="running",
            progress=1,
            error=None,
        )


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
        """空数据库时状态 API 从第一步开始，并公开五步进度。"""
        resp = client.get("/api/auth/setup-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["need_setup"] is True
        assert data["complete"] is False
        assert data["current_step"] == 1
        assert [step["number"] for step in data["steps"]] == [1, 2, 3, 4, 5]
        assert data["steps"][0]["status"] == "pending"

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
                json={"username": "owner", "password": "securePass123"},
            )

        assert response.status_code == 403

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
            json={"username": "owner", "password": "securePass123"},
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

    def test_setup_can_complete_the_remaining_four_steps_with_explicit_skips(
        self, client: TestClient
    ) -> None:
        owner = client.post(
            "/api/auth/setup",
            json={"username": "owner", "password": "securePass123"},
        )
        csrf = owner.json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf}

        offline = client.post(
            "/api/auth/setup/ollama",
            json={"decision": "skipped"},
            headers=headers,
        )
        nest = client.put(
            "/api/auth/setup/nest",
            json={"bed_count": 4},
            headers=headers,
        )
        model = client.post(
            "/api/auth/setup/model",
            json={"decision": "skipped"},
            headers=headers,
        )
        complete = client.post("/api/auth/setup/complete", headers=headers)

        assert offline.status_code == 200, offline.text
        assert nest.status_code == 200, nest.text
        assert model.status_code == 200, model.text
        assert complete.status_code == 200, complete.text
        assert client.get("/api/auth/setup-status").json()["complete"] is True

        resp = client.post(
            "/api/auth/setup",
            json={"username": "owner", "password": "securePass123", "avatar_color": -1},
        )
        assert resp.status_code == 422

    def test_setup_ollama_install_requires_confirmation_and_queues_background_job(
        self, client: TestClient, app
    ) -> None:
        """确认安装只排队固定官方任务，不在请求内下载或执行脚本。"""
        owner = client.post(
            "/api/auth/setup",
            json={"username": "owner", "password": "securePass123"},
        )
        headers = {"X-CSRF-Token": owner.json()["csrf_token"]}
        jobs = _QueuedOllamaJobs()
        app.state.setup_ollama_jobs = jobs

        rejected = client.post(
            "/api/auth/setup/ollama/install",
            json={"confirmed": False},
            headers=headers,
        )
        accepted = client.post(
            "/api/auth/setup/ollama/install",
            json={"confirmed": True},
            headers=headers,
        )

        assert rejected.status_code == 422
        assert accepted.status_code == 202, accepted.text
        assert accepted.json()["task"]["state"] == "running"
        assert jobs.started

    def test_setup_model_recommendation_never_recommends_ollama_below_four_gb(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """低内存设备只能看到可跳过说明，不能被默认强推本地模型。"""
        owner = client.post(
            "/api/auth/setup",
            json={"username": "owner", "password": "securePass123"},
        )
        headers = {"X-CSRF-Token": owner.json()["csrf_token"]}
        monkeypatch.setattr(
            "app.interfaces.api.setup_routes.get_available_memory_gb", lambda: 3
        )

        response = client.get("/api/auth/setup/model-recommendation", headers=headers)

        assert response.status_code == 200
        assert response.json() == {"memory_gb": 3, "recommended_model": None}

    def test_setup_model_rejects_implicit_provider_reference(
        self, client: TestClient
    ) -> None:
        """模型步骤不能把裸模型名偷偷默认成 Ollama。"""
        owner = client.post(
            "/api/auth/setup",
            json={"username": "owner", "password": "securePass123"},
        )
        headers = {"X-CSRF-Token": owner.json()["csrf_token"]}
        client.post(
            "/api/auth/setup/ollama",
            json={"decision": "skipped"},
            headers=headers,
        )
        client.put(
            "/api/auth/setup/nest",
            json={"bed_count": 4},
            headers=headers,
        )

        response = client.post(
            "/api/auth/setup/model",
            json={"decision": "configured", "model_reference": "qwen2.5:0.5b"},
            headers=headers,
        )

        assert response.status_code == 422
        assert "provider_id/model_id" in response.text

    def test_setup_model_pull_requires_confirmation_and_queues_work(
        self, client: TestClient, app
    ) -> None:
        """模型下载需要明确确认，HTTP 请求只入队而不阻塞下载。"""
        owner = client.post(
            "/api/auth/setup",
            json={"username": "owner", "password": "securePass123"},
        )
        headers = {"X-CSRF-Token": owner.json()["csrf_token"]}
        client.post(
            "/api/auth/setup/ollama",
            json={"decision": "skipped"},
            headers=headers,
        )
        client.put(
            "/api/auth/setup/nest",
            json={"bed_count": 4},
            headers=headers,
        )
        jobs = _QueuedOllamaJobs()
        app.state.setup_ollama_jobs = jobs

        rejected = client.post(
            "/api/auth/setup/model/pull",
            json={"model_reference": "ollama/qwen2.5:0.5b", "confirmed": False},
            headers=headers,
        )
        accepted = client.post(
            "/api/auth/setup/model/pull",
            json={"model_reference": "ollama/qwen2.5:0.5b", "confirmed": True},
            headers=headers,
        )

        assert rejected.status_code == 422
        assert accepted.status_code == 202, accepted.text
        assert accepted.json()["task"]["key"] == "model_pull"
        assert jobs.started
