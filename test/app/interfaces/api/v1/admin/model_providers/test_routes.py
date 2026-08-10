from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.accounts import AccountPrincipal, AccountRole
from app.features.configuration import ProvidersService
from app.interfaces.api.v1.admin.model_providers.routes import router
from app.interfaces.api.v1.auth import require_user
from infrastructure.models import ProviderModelsAdapter


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


def _principal(role: AccountRole = "owner") -> AccountPrincipal:
    return AccountPrincipal(1, "owner", role, "/manage")


def _client(tmp_path, monkeypatch, role: AccountRole = "owner") -> TestClient:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    adapter = ProviderModelsAdapter(
        tmp_path / "providers.yaml",
        tmp_path / "auth.env",
    )
    application = FastAPI()
    application.state.providers = ProvidersService(
        catalog=adapter,
        connections=adapter,
        references=NoProviderReferences(),
        technology=adapter,
    )
    application.dependency_overrides[require_user] = lambda: _principal(role)
    application.include_router(router)
    return TestClient(application)


def test_versioned_provider_create_and_list_use_strict_envelopes(
    tmp_path,
    monkeypatch,
) -> None:
    client = _client(tmp_path, monkeypatch)

    created = client.post(
        "/api/v1/admin/model-providers/connections",
        json={
            "catalog_id": "openai_api",
            "alias": "Primary",
            "api_key": "test-secret",
            "models": [{"id": "gpt-test"}],
        },
    )
    listed = client.get("/api/v1/admin/model-providers/connections")

    assert created.status_code == 201
    assert created.json()["connection_id"] == "openai_api_0001"
    assert created.json()["has_api_key"] is True
    assert "test-secret" not in created.text
    assert listed.status_code == 200
    assert {item["catalog_id"] for item in listed.json()["items"]} == {
        "ollama",
        "openai_api",
    }


def test_versioned_provider_rejects_unknown_fields_before_persistence(
    tmp_path,
    monkeypatch,
) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/v1/admin/model-providers/connections",
        json={"catalog_id": "openai_api", "unexpected": True},
    )

    assert response.status_code == 422
    assert not (tmp_path / "providers.yaml").exists()


def test_versioned_provider_authorization_is_enforced_in_feature(
    tmp_path,
    monkeypatch,
) -> None:
    client = _client(tmp_path, monkeypatch, role="user")

    response = client.get("/api/v1/admin/model-providers/catalog")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "model_providers_forbidden"


def test_versioned_provider_has_only_named_model_resources(
    tmp_path,
    monkeypatch,
) -> None:
    client = _client(tmp_path, monkeypatch)

    paths = {route.path for route in client.app.routes}

    assert "/api/v1/admin/model-providers/model-matrix" in paths
    assert "/api/v1/admin/model-providers/model-benchmarks" in paths
    assert "/api/v1/admin/model-providers/model-validations" in paths
    assert "/api/v1/admin/model-providers/{section}" not in paths
