"""Regression coverage for the legacy Ollama-only Provider subresource."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from ai_runtime.storage.provider_connections import ProviderConnectionStore
from app.bootstrap import create_app
from app.infrastructure.ollama_platform import OllamaBinding, OllamaProbe
from app.infrastructure.persistence.store import init_db

from ._helpers import create_test_owner


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_test_owner(db_path)
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        with TestClient(application) as test_client:
            yield test_client


def _login(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        data={"account_id": "owner", "password": "ownerchangeme"},
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": response.headers["X-CSRF-Token"]}


def test_ollama_management_status_is_always_available_as_a_local_resource(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _login(client)
    monkeypatch.setattr(
        "app.interfaces.api.ollama_owner_routes.OllamaPlatformAdapter",
        _AbsentOllamaAdapter,
    )

    response = client.get("/api/owner/providers/ollama", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "absent"
    assert payload["installed_model_count"] == 0
    assert [model["id"] for model in payload["models"]] == [
        "qwen2.5:0.5b",
        "qwen3.5:0.8b",
        "gemma3:270m",
    ]


def test_ollama_start_records_a_healthy_default_binding(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _login(client)
    monkeypatch.setattr(
        "app.interfaces.api.ollama_owner_routes.OllamaPlatformAdapter",
        _HealthyOllamaAdapter,
    )

    response = client.post("/api/owner/providers/ollama/start", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "healthy"
    saved = ProviderConnectionStore().load().connections["ollama_0001"]
    assert saved.installation["install_kind"] == "existing-public"


def test_ollama_model_download_updates_the_local_model_list(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _login(client)
    monkeypatch.setattr(
        "app.interfaces.api.ollama_owner_routes.OllamaPlatformAdapter",
        _PullingOllamaAdapter,
    )

    response = client.post(
        "/api/owner/providers/ollama/models/pull",
        headers=headers,
        json={"model_ids": ["qwen3.5:0.8b"], "confirmed": True},
    )

    assert response.status_code == 200, response.text
    listed = client.get("/api/owner/providers/ollama", headers=headers)
    assert listed.status_code == 200
    models = {model["id"]: model for model in listed.json()["models"]}
    assert models["qwen3.5:0.8b"]["installed"] is True


class _AbsentOllamaAdapter:
    platform = "linux"

    def probe(self, binding: OllamaBinding | None) -> OllamaProbe:
        endpoint = binding.api_base if binding is not None else "http://127.0.0.1:11434"
        return OllamaProbe("absent", endpoint)

    def list_models(self, binding: OllamaBinding) -> tuple[str, ...]:
        _ = binding
        return ()


class _HealthyOllamaAdapter(_AbsentOllamaAdapter):
    def probe(self, binding: OllamaBinding | None) -> OllamaProbe:
        endpoint = binding.api_base if binding is not None else "http://127.0.0.1:11434"
        return OllamaProbe("healthy", endpoint, version="0.12.0")

    def start_bound_installation(self, binding: OllamaBinding) -> None:
        _ = binding


class _PullingOllamaAdapter(_HealthyOllamaAdapter):
    models: list[str] = []

    def list_models(self, binding: OllamaBinding) -> tuple[str, ...]:
        _ = binding
        return tuple(self.models)

    def pull_model(self, binding: OllamaBinding, model_id: str) -> None:
        _ = binding
        self.models.append(model_id)
