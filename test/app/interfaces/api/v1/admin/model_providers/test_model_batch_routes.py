from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.accounts import AccountPrincipal
from app.features.configuration import ProvidersService
from app.interfaces.api.v1.admin.model_providers.routes import router
from app.interfaces.api.v1.auth import require_user
from infrastructure.models.ollama.provider_ollama import PublicOllamaProviderAdapter
from infrastructure.persistence.provider_catalog import load_provider_catalog
from infrastructure.persistence.provider_connections import (
    ProviderConnectionStore,
    ProviderModelRecord,
)
from infrastructure.persistence.reports.validation_reports import (
    write_model_validation_report,
)
from test.support.provider import provider_models_adapter


class NoProviderReferences:
    def connections_referenced_by_food(self, connection_id: str) -> tuple[str, ...]:
        _ = connection_id
        return ()

    def models_referenced_by_food(
        self,
        connection_id: str,
        model_id: str,
    ) -> tuple[str, ...]:
        _ = connection_id, model_id
        return ()


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    adapter = provider_models_adapter()
    application = FastAPI()
    application.state.providers = ProvidersService(
        catalog=adapter,
        connections=adapter,
        references=NoProviderReferences(),
        technology=adapter,
        local_state=adapter,
        local_technology=PublicOllamaProviderAdapter(catalog=load_provider_catalog()),
    )
    application.dependency_overrides[require_user] = lambda: AccountPrincipal(
        1,
        "owner",
        "owner",
        "/manage",
    )
    application.include_router(router)
    with TestClient(application) as test_client:
        yield test_client


def test_model_list_save_updates_every_row_and_projects_latest_validation(
    client: TestClient,
) -> None:
    connection_id = _create_connection(client)
    store = ProviderConnectionStore()
    connection = store.load().connections[connection_id]
    store.replace(
        replace(
            connection,
            models=(
                ProviderModelRecord(endpoint_model_id="auto-model", source="official"),
                ProviderModelRecord(endpoint_model_id="manual-model", source="manual"),
            ),
        )
    )
    write_model_validation_report(
        connection_id,
        "auto-model",
        status="passed",
        checked_at="2026-08-03T01:02:03+00:00",
        latency_ms=123.4,
        latency_class="normal",
        error=None,
        trigger="full",
        details={"validation_mode": "full"},
    )

    response = client.put(
        f"/api/v1/admin/model-providers/connections/{connection_id}/models",
        json={
            "models": [
                _model_payload("auto-model", display_name="Auto", hidden=False),
                _model_payload(
                    "manual-model",
                    display_name="Manual Updated",
                    hidden=True,
                    supports_tools=True,
                ),
            ]
        },
    )

    assert response.status_code == 200, response.text
    models = {model["id"]: model for model in response.json()["models"]}
    assert models["manual-model"]["display_name"] == "Manual Updated"
    assert models["manual-model"]["hidden"] is True
    assert models["auto-model"]["verification"]["status"] == "passed"
    assert models["auto-model"]["verification"]["latency_ms"] == 123.4
    assert models["auto-model"]["verification"]["validation_mode"] == "full"


def test_model_list_save_rejects_automatic_id_change_without_partial_persistence(
    client: TestClient,
) -> None:
    connection_id = _create_connection(client)
    store = ProviderConnectionStore()
    connection = store.load().connections[connection_id]
    store.replace(
        replace(
            connection,
            models=(
                ProviderModelRecord(endpoint_model_id="auto-model", source="official"),
                ProviderModelRecord(endpoint_model_id="manual-model", source="manual"),
            ),
        )
    )

    response = client.put(
        f"/api/v1/admin/model-providers/connections/{connection_id}/models",
        json={
            "models": [
                _model_payload("auto-renamed", original_id="auto-model"),
                _model_payload("manual-model"),
            ]
        },
    )

    assert response.status_code == 422
    persisted = ProviderConnectionStore().load().connections[connection_id]
    assert [model.endpoint_model_id for model in persisted.models] == [
        "auto-model",
        "manual-model",
    ]


def test_model_list_save_rejects_duplicate_target_id_without_partial_persistence(
    client: TestClient,
) -> None:
    connection_id = _create_connection(client)
    store = ProviderConnectionStore()
    connection = store.load().connections[connection_id]
    store.replace(
        replace(
            connection,
            models=(
                ProviderModelRecord(endpoint_model_id="first-model"),
                ProviderModelRecord(endpoint_model_id="second-model"),
            ),
        )
    )

    response = client.put(
        f"/api/v1/admin/model-providers/connections/{connection_id}/models",
        json={
            "models": [
                _model_payload("same-model", original_id="first-model"),
                _model_payload("same-model", original_id="second-model"),
            ]
        },
    )

    assert response.status_code == 422
    persisted = ProviderConnectionStore().load().connections[connection_id]
    assert [model.endpoint_model_id for model in persisted.models] == [
        "first-model",
        "second-model",
    ]


def test_model_list_save_rejects_nonpositive_limit_before_persistence(
    client: TestClient,
) -> None:
    connection_id = _create_connection(client)
    response = client.put(
        f"/api/v1/admin/model-providers/connections/{connection_id}/models",
        json={
            "models": [
                {
                    **_model_payload("seed-model"),
                    "context_window_tokens": 0,
                }
            ]
        },
    )

    assert response.status_code == 422
    persisted = ProviderConnectionStore().load().connections[connection_id]
    assert [model.endpoint_model_id for model in persisted.models] == ["seed-model"]


def test_model_list_save_rejects_blank_model_id_before_persistence(
    client: TestClient,
) -> None:
    connection_id = _create_connection(client)

    response = client.put(
        f"/api/v1/admin/model-providers/connections/{connection_id}/models",
        json={"models": [_model_payload(" ", original_id="seed-model")]},
    )

    assert response.status_code == 422
    persisted = ProviderConnectionStore().load().connections[connection_id]
    assert [model.endpoint_model_id for model in persisted.models] == ["seed-model"]


def _create_connection(client: TestClient) -> str:
    response = client.post(
        "/api/v1/admin/model-providers/connections",
        json={
            "catalog_id": "custom_openai",
            "alias": "Batch Test",
            "api_base": "https://gateway.example/v1",
            "verify": False,
            "models": [{"id": "seed-model"}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["connection_id"]


def _model_payload(
    model_id: str,
    *,
    original_id: str | None = None,
    display_name: str = "Model",
    hidden: bool = False,
    supports_tools: bool | None = None,
) -> dict[str, str | bool | None]:
    return {
        "original_id": original_id or model_id,
        "id": model_id,
        "display_name": display_name,
        "canonical_model_id": None,
        "context_window_tokens": None,
        "max_output_tokens": None,
        "supports_tools": supports_tools,
        "supports_vision": None,
        "supports_reasoning": None,
        "hidden": hidden,
    }
