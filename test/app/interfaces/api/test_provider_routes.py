"""Owner API contract for Provider catalog products and v2 connections."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from ai_runtime.food.evidence import record_model_evidence
from ai_runtime.food.planner import ModelEvidence
from ai_runtime.storage.data_home import get_provider_config_path
from ai_runtime.storage.provider_connections import (
    ProviderConnection,
    ProviderConnectionStore,
    ProviderModelRecord,
)
from ai_runtime.storage.report_repository import ReportRepository
from ai_runtime.validation.providers import DiscoveredModel
from app.infrastructure.ollama_platform import OllamaBinding, OllamaProbe
from app.infrastructure.persistence.store import init_db
from app.interfaces.api.app import create_app
from app.interfaces.api.provider_connection_model_routes import (
    validate_all_connection_models,
)

from ._helpers import create_test_owner, create_test_user


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_test_owner(db_path)
    create_test_user(db_path, "alice", "pass123")
    create_test_user(db_path, "admin", "pass123", role="admin")
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        with TestClient(application) as test_client:
            yield test_client


def _login(client: TestClient, account_id: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        data={"account_id": account_id, "password": password},
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": response.headers["X-CSRF-Token"]}


def _create_connection(
    client: TestClient,
    headers: dict[str, str],
    *,
    alias: str,
    api_key: str = "",
) -> dict[str, object]:
    response = client.post(
        "/api/owner/providers/connections",
        headers=headers,
        json={
            "catalog_id": "custom_openai",
            "alias": alias,
            "api_base": "https://gateway.example/v1",
            "api_key": api_key,
            "verify": False,
            "models": [{"id": "model-a", "display_name": "Model A"}],
        },
    )
    assert response.status_code == 201
    return response.json()


def test_catalog_and_connections_are_separate_resources(client: TestClient) -> None:
    headers = _login(client, "owner", "ownerchangeme")

    catalog = client.get("/api/owner/providers/catalog", headers=headers)
    connections = client.get("/api/owner/providers/connections", headers=headers)

    assert catalog.status_code == 200
    assert {item["catalog_id"] for item in catalog.json()} >= {
        "ollama",
        "custom_openai",
    }
    assert connections.status_code == 200
    assert connections.json()[0]["connection_id"] == "ollama_0001"


def test_ollama_management_status_is_always_available_as_a_local_resource(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _login(client, "owner", "ownerchangeme")
    monkeypatch.setattr(
        "app.interfaces.api.ollama_owner_routes.OllamaPlatformAdapter",
        _AbsentOllamaAdapter,
    )

    response = client.get("/api/owner/providers/ollama", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "absent"
    assert payload["installed_model_count"] == 0
    assert payload["models"][0]["id"] == "qwen3.5:0.8b"


def test_ollama_start_connects_a_healthy_default_endpoint_and_records_the_binding(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _login(client, "owner", "ownerchangeme")
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
    headers = _login(client, "owner", "ownerchangeme")
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


def test_same_product_gets_stable_ids_and_alias_update_keeps_identity(
    client: TestClient,
) -> None:
    headers = _login(client, "owner", "ownerchangeme")
    first = _create_connection(client, headers, alias="Work")
    second = _create_connection(client, headers, alias="Personal")

    updated = client.put(
        f"/api/owner/providers/connections/{first['connection_id']}",
        headers=headers,
        json={"alias": "Renamed Work", "verify": False},
    )

    assert first["connection_id"] == "custom_openai_0001"
    assert second["connection_id"] == "custom_openai_0002"
    assert updated.status_code == 200
    assert updated.json()["connection_id"] == first["connection_id"]
    assert updated.json()["alias"] == "Renamed Work"


def test_connection_secret_is_never_returned_or_written_to_provider_yaml(
    client: TestClient,
) -> None:
    headers = _login(client, "owner", "ownerchangeme")
    secret = "provider-test-secret-value"

    created = _create_connection(client, headers, alias="Secret", api_key=secret)
    listed = client.get("/api/owner/providers/connections", headers=headers)
    serialized_response = json.dumps(listed.json(), ensure_ascii=False)
    provider_yaml = get_provider_config_path().read_text(encoding="utf-8")

    assert created["has_api_key"] is True
    assert "api_key" not in created
    assert "credential_ref" not in created
    assert secret not in serialized_response
    assert secret not in provider_yaml
    assert "api_key:" not in provider_yaml


def test_model_matrix_reads_the_same_new_sqlite_evidence_immediately(
    client: TestClient,
) -> None:
    headers = _login(client, "owner", "ownerchangeme")
    created = _create_connection(client, headers, alias="Matrix")
    subject_id = f"{created['connection_id']}/model-a"
    record_model_evidence(
        (
            ModelEvidence(
                subject_id,
                frozenset({"text"}),
                True,
                observed_at=datetime.now(timezone.utc).isoformat(),
            ),
        ),
        scope="api-test",
        trigger="benchmark",
    )

    response = client.get(
        "/api/owner/providers/connection-model-matrix",
        headers=headers,
    )

    assert response.status_code == 200
    model = next(
        item for item in response.json()["models"] if item["display_name"] == "Model A"
    )
    cell = next(
        item
        for item in model["connections"]
        if item["connection_id"] == created["connection_id"]
    )
    assert cell["benchmark_status"] == "passed"


def test_model_matrix_run_snapshot_preserves_observed_status_and_latency_class(
    client: TestClient,
) -> None:
    headers = _login(client, "owner", "ownerchangeme")
    created = _create_connection(client, headers, alias="Historical Matrix")
    repository = ReportRepository()
    run_id = repository.start_run(
        scope="single_model",
        trigger="benchmark",
        started_at="2025-01-01T00:00:00+00:00",
    )
    repository.append_observation(
        run_id=run_id,
        subject_kind="model",
        subject_id=f"{created['connection_id']}/model-a",
        observed_at="2025-01-01T00:00:01+00:00",
        status="passed",
        latency_ms=42.0,
        details={"latency_class": "fast"},
    )
    repository.finish_run(
        run_id,
        status="complete",
        finished_at="2025-01-01T00:00:02+00:00",
    )
    later_run_id = repository.start_run(
        scope="single_provider",
        trigger="manual",
        started_at="2025-01-02T00:00:00+00:00",
    )
    repository.append_observation(
        run_id=later_run_id,
        subject_kind="provider",
        subject_id=str(created["connection_id"]),
        observed_at="2025-01-02T00:00:01+00:00",
        status="passed",
    )
    repository.finish_run(
        later_run_id,
        status="complete",
        finished_at="2025-01-02T00:00:02+00:00",
    )

    response = client.get(
        "/api/owner/providers/connection-model-matrix",
        headers=headers,
        params={"run_id": run_id},
    )

    assert response.status_code == 200
    model = next(
        item for item in response.json()["models"] if item["display_name"] == "Model A"
    )
    cell = next(
        item
        for item in model["connections"]
        if item["connection_id"] == created["connection_id"]
    )
    assert cell["benchmark_status"] == "passed"
    assert cell["latency_ms"] == 42.0
    assert cell["latency_class"] == "fast"
    connection = next(
        item
        for item in response.json()["connections"]
        if item["connection_id"] == created["connection_id"]
    )
    assert connection["verification"]["status"] == "never"


def test_old_provider_crud_routes_are_not_available(client: TestClient) -> None:
    headers = _login(client, "owner", "ownerchangeme")

    assert client.get("/api/owner/providers", headers=headers).status_code == 404
    assert (
        client.post(
            "/api/owner/providers/openai",
            headers=headers,
            json={"api_key": "unused"},
        ).status_code
        == 404
    )
    assert client.get("/api/owner/models", headers=headers).status_code == 404


def test_provider_routes_require_owner_role(client: TestClient) -> None:
    headers = _login(client, "alice", "pass123")

    response = client.get("/api/owner/providers/connections", headers=headers)

    assert response.status_code == 403


def test_provider_routes_accept_admin_role(client: TestClient) -> None:
    headers = _login(client, "admin", "pass123")

    response = client.get("/api/owner/providers/connections", headers=headers)

    assert response.status_code == 200


def test_provider_routes_require_authentication(client: TestClient) -> None:
    response = client.get("/api/owner/providers/connections")

    assert response.status_code == 401


def test_unknown_fields_are_rejected_without_persisting_connection(
    client: TestClient,
) -> None:
    headers = _login(client, "owner", "ownerchangeme")

    response = client.post(
        "/api/owner/providers/connections",
        headers=headers,
        json={
            "catalog_id": "custom_openai",
            "alias": "Invalid",
            "api_base": "https://gateway.example/v1",
            "provider_id": "legacy-shape",
            "verify": False,
        },
    )

    assert response.status_code == 422
    provider_path = get_provider_config_path()
    assert not provider_path.exists() or "custom_openai_0001" not in (
        provider_path.read_text(encoding="utf-8")
    )


def test_refresh_uses_bundled_catalog_after_empty_remote_and_preserves_manual_model(
    client: TestClient,
) -> None:
    headers = _login(client, "owner", "ownerchangeme")
    created = client.post(
        "/api/owner/providers/connections",
        headers=headers,
        json={
            "catalog_id": "openai_api",
            "alias": "Fallback chain",
            "api_key": "test-key",
            "verify": False,
            "models": [{"id": "manual-kept", "display_name": "Manual kept"}],
        },
    )
    assert created.status_code == 201

    with (
        patch(
            "app.interfaces.api.provider_connection_routes._discover_with_slot",
            side_effect=RuntimeError("official unavailable"),
        ),
        patch(
            "app.interfaces.api.provider_connection_routes.fetch_remote_models",
            return_value=(),
        ),
    ):
        response = client.post(
            f"/api/owner/providers/connections/{created.json()['connection_id']}/models/refresh",
            headers=headers,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "bundled_catalog"
    models = {model["id"]: model for model in payload["models"]}
    assert models["manual-kept"]["source"] == "manual"
    assert any(model["source"] == "bundled_catalog" for model in models.values())


def test_refresh_keeps_first_nonempty_official_result(
    client: TestClient,
) -> None:
    headers = _login(client, "owner", "ownerchangeme")
    created = client.post(
        "/api/owner/providers/connections",
        headers=headers,
        json={
            "catalog_id": "openai_api",
            "alias": "Official first",
            "api_key": "test-key",
            "verify": False,
        },
    )
    assert created.status_code == 201

    with (
        patch(
            "app.interfaces.api.provider_connection_routes._discover_with_slot",
            return_value=[DiscoveredModel("openai", "official-model")],
        ),
        patch(
            "app.interfaces.api.provider_connection_routes.fetch_remote_models",
            side_effect=AssertionError("remote adapter must not run"),
        ),
    ):
        response = client.post(
            f"/api/owner/providers/connections/{created.json()['connection_id']}/models/refresh",
            headers=headers,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "updated"
    assert payload["models"] == [
        {
            "id": "official-model",
            "display_name": "official-model",
            "canonical_model_id": None,
            "source": "official",
            "context_window_tokens": None,
            "max_output_tokens": None,
            "supports_tools": None,
            "supports_vision": None,
            "supports_reasoning": None,
            "hidden": False,
            "retired": False,
            "available": True,
        }
    ]


def test_refresh_uses_first_nonempty_configured_remote_adapter(
    client: TestClient,
) -> None:
    headers = _login(client, "owner", "ownerchangeme")
    created = client.post(
        "/api/owner/providers/connections",
        headers=headers,
        json={
            "catalog_id": "openai_api",
            "alias": "Remote second",
            "api_key": "test-key",
            "verify": False,
        },
    )
    assert created.status_code == 201

    with (
        patch(
            "app.interfaces.api.provider_connection_routes._discover_with_slot",
            side_effect=RuntimeError("official unavailable"),
        ),
        patch(
            "app.interfaces.api.provider_connection_routes.fetch_remote_models",
            return_value=("remote-model",),
        ),
    ):
        response = client.post(
            f"/api/owner/providers/connections/{created.json()['connection_id']}/models/refresh",
            headers=headers,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "remote_catalog"
    assert {model["source"] for model in payload["models"]} == {"remote_catalog"}


class _RunSpy:
    def __init__(self) -> None:
        self.finished_status: str | None = None

    def start_run(self, **_: str) -> str:
        return "run_test"

    def finish_run(self, _: str, *, status: str, finished_at: str) -> None:
        self.finished_status = status


class _ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


class _DisconnectedRequest:
    async def is_disconnected(self) -> bool:
        return True


def test_validate_all_finalizes_partial_run_after_disconnect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    ProviderConnectionStore().replace(
        ProviderConnection(
            connection_id="custom_openai_0001",
            catalog_id="custom_openai",
            alias="Disconnected",
            models=(ProviderModelRecord(endpoint_model_id="model-a"),),
        )
    )
    run = _RunSpy()

    with patch(
        "app.interfaces.api.provider_connection_model_routes.ReportRepository",
        return_value=run,
    ):
        payload = asyncio.run(
            validate_all_connection_models(_DisconnectedRequest(), owner={})
        )

    assert payload["status"] == "partial"
    assert run.finished_status == "partial"


def test_validate_all_finalizes_partial_run_after_cancellation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    ProviderConnectionStore().replace(
        ProviderConnection(
            connection_id="custom_openai_0001",
            catalog_id="custom_openai",
            alias="Cancelled",
            models=(ProviderModelRecord(endpoint_model_id="model-a"),),
        )
    )
    run = _RunSpy()

    with (
        patch(
            "app.interfaces.api.provider_connection_model_routes.ReportRepository",
            return_value=run,
        ),
        patch(
            "app.interfaces.api.provider_connection_model_routes._verify_connection_in_run",
            new=AsyncMock(side_effect=asyncio.CancelledError),
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        asyncio.run(validate_all_connection_models(_ConnectedRequest(), owner={}))

    assert run.finished_status == "partial"


def test_validate_all_finalizes_failed_run_after_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    ProviderConnectionStore().replace(
        ProviderConnection(
            connection_id="custom_openai_0001",
            catalog_id="custom_openai",
            alias="Broken",
            models=(ProviderModelRecord(endpoint_model_id="model-a"),),
        )
    )
    run = _RunSpy()

    with (
        patch(
            "app.interfaces.api.provider_connection_model_routes.ReportRepository",
            return_value=run,
        ),
        patch(
            "app.interfaces.api.provider_connection_model_routes._verify_connection_in_run",
            new=AsyncMock(side_effect=RuntimeError("connection broken")),
        ),
        pytest.raises(RuntimeError, match="connection broken"),
    ):
        asyncio.run(validate_all_connection_models(_ConnectedRequest(), owner={}))

    assert run.finished_status == "failed"
