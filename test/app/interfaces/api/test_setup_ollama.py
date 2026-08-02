"""Setup Ollama/model-step API tests isolated from the core Setup contract."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.interfaces.api.app import create_app


class _QueuedOllamaJobs:
    """Avoid a real network/download while proving the request only queues work."""

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
    with TestClient(app, base_url="http://127.0.0.1:8000") as test_client:
        yield test_client


def _owner_headers(client: TestClient) -> dict[str, str]:
    owner = client.post(
        "/api/auth/setup",
        json={"account_id": "owner", "password": "securePass123"},
    )
    assert owner.status_code == 201, owner.text
    return {"X-CSRF-Token": owner.json()["csrf_token"]}


def test_setup_ollama_install_requires_confirmation_and_queues_background_job(
    client: TestClient, app
) -> None:
    """确认安装只排队固定官方任务，不在请求内下载或执行脚本。"""
    headers = _owner_headers(client)
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
    client: TestClient, monkeypatch: pytest.MonkeyPatch, app
) -> None:
    """低内存设备只能看到可跳过说明，不能被默认强推本地模型。"""
    headers = _owner_headers(client)
    monkeypatch.setattr(
        "app.interfaces.api.setup_routes.get_available_memory_gb", lambda: 3
    )

    response = client.get("/api/auth/setup/model-recommendation", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"memory_gb": 3, "recommended_model": None}


def test_setup_model_rejects_implicit_provider_reference(
    client: TestClient, app
) -> None:
    """模型步骤不能把裸模型名偷偷默认成 Ollama。"""
    headers = _owner_headers(client)
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
    assert "connection_id/model_id" in response.text


def test_setup_model_pull_requires_confirmation_and_queues_work(
    client: TestClient, app
) -> None:
    """模型下载需要明确确认，HTTP 请求只入队而不阻塞下载。"""
    headers = _owner_headers(client)
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
