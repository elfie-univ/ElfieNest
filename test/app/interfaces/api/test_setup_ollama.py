"""Setup Ollama/model-step API tests isolated from the core Setup contract."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.infrastructure.ollama_platform import OllamaBinding, OllamaProbe

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
    with TestClient(app, base_url="http://127.0.0.1:8000") as test_client:
        yield test_client


def _owner_headers(client: TestClient) -> dict[str, str]:
    create_test_owner(client.app.state.db_path, password="ownerchangeme")
    owner = client.post(
        "/api/v1/auth/login",
        data={"account_id": "owner", "password": "ownerchangeme"},
    )
    assert owner.status_code == 200, owner.text
    return {"X-CSRF-Token": owner.headers["X-CSRF-Token"]}


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
    assert response.json() == {
        "memory_gb": 3,
        "recommended_model": None,
        "ollama_state": "absent",
        "ollama_endpoint": None,
        "installed_models": [],
        "recommended_model_available": False,
    }


def test_setup_model_recommendation_marks_an_installed_local_model(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An already downloaded target is surfaced as ready-to-use, not as a download suggestion."""
    headers = _owner_headers(client)
    monkeypatch.setattr(
        "app.interfaces.api.setup_routes.get_available_memory_gb", lambda: 16
    )
    monkeypatch.setattr(
        "app.interfaces.api.setup_routes.OllamaPlatformAdapter",
        _HealthyRecommendationAdapter,
    )

    response = client.get("/api/auth/setup/model-recommendation", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "memory_gb": 16,
        "recommended_model": "ollama/qwen2.5:3b",
        "ollama_state": "healthy",
        "ollama_endpoint": "http://127.0.0.1:11434",
        "installed_models": ["qwen2.5:3b"],
        "recommended_model_available": True,
    }


def test_setup_ollama_detection_reports_a_healthy_default_endpoint(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _owner_headers(client)
    monkeypatch.setattr(
        "app.interfaces.api.setup_routes.OllamaPlatformAdapter",
        _HealthyRecommendationAdapter,
    )

    response = client.get("/api/auth/setup/ollama-detection", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "state": "healthy",
        "endpoint": "http://127.0.0.1:11434",
        "version": "0.12.0",
    }


class _HealthyRecommendationAdapter:
    platform = "linux"

    def probe(self, binding: OllamaBinding | None) -> OllamaProbe:
        assert binding is not None
        return OllamaProbe("healthy", binding.api_base, version="0.12.0")

    def list_models(self, binding: OllamaBinding) -> tuple[str, ...]:
        assert binding.api_base == "http://127.0.0.1:11434"
        return ("qwen2.5:3b",)
