from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_runtime.food.evidence import record_model_evidence
from ai_runtime.food.planner import ModelEvidence
from ai_runtime.storage.report_repository import ReportRepository
from ai_runtime.validation.providers import DiscoveredModel
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
    local_provider = adapter.get_product("ollama")
    assert local_provider is not None
    adapter.ensure_local_connection(local_provider)
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


def _anonymous_client(tmp_path, monkeypatch) -> TestClient:
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
    application.include_router(router)
    return TestClient(application)


def _create_connection(
    client: TestClient,
    *,
    alias: str,
    catalog_id: str = "custom_openai",
) -> dict[str, object]:
    response = client.post(
        "/api/v1/admin/model-providers/connections",
        json={
            "catalog_id": catalog_id,
            "alias": alias,
            "api_base": (
                "https://gateway.example/v1" if catalog_id == "custom_openai" else None
            ),
            "models": [{"id": "model-a", "display_name": "Model A"}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


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
    listed = client.get("/api/v1/admin/model-providers/connections")

    assert response.status_code == 422
    assert {item["catalog_id"] for item in listed.json()["items"]} == {"ollama"}


def test_versioned_provider_authorization_is_enforced_in_feature(
    tmp_path,
    monkeypatch,
) -> None:
    client = _client(tmp_path, monkeypatch, role="user")

    response = client.get("/api/v1/admin/model-providers/catalog")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "model_providers_forbidden"


def test_versioned_provider_accepts_admin_and_requires_authentication(
    tmp_path,
    monkeypatch,
) -> None:
    admin = _client(tmp_path, monkeypatch, role="admin")
    anonymous = _anonymous_client(tmp_path, monkeypatch)

    assert admin.get("/api/v1/admin/model-providers/catalog").status_code == 200
    assert anonymous.get("/api/v1/admin/model-providers/catalog").status_code == 401


def test_connection_identity_is_stable_across_alias_update(
    tmp_path,
    monkeypatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    first = _create_connection(client, alias="Work")
    second = _create_connection(client, alias="Personal")

    updated = client.patch(
        f"/api/v1/admin/model-providers/connections/{first['connection_id']}",
        json={"alias": "Renamed Work"},
    )

    assert first["connection_id"] == "custom_openai_0001"
    assert second["connection_id"] == "custom_openai_0002"
    assert updated.status_code == 200
    assert updated.json()["connection_id"] == first["connection_id"]
    assert updated.json()["alias"] == "Renamed Work"


def test_create_does_not_verify_unless_requested(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    with patch.object(
        ProviderModelsAdapter,
        "verify_connection",
        new=AsyncMock(),
    ) as verification:
        created = _create_connection(client, alias="Save only")

    assert created["connection_id"] == "custom_openai_0001"
    verification.assert_not_awaited()


def test_model_matrix_reads_current_and_historical_sqlite_evidence(
    tmp_path,
    monkeypatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    created = _create_connection(client, alias="Matrix")
    connection_id = str(created["connection_id"])
    subject_id = f"{connection_id}/model-a"
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

    current = client.get("/api/v1/admin/model-providers/model-matrix")
    assert current.status_code == 200, current.text
    current_model = next(
        item for item in current.json()["models"] if item["display_name"] == "Model A"
    )
    current_cell = next(
        item
        for item in current_model["connections"]
        if item["connection_id"] == connection_id
    )
    assert current_cell["benchmark_status"] == "passed"

    repository = ReportRepository()
    run_id = repository.start_run(
        scope="single_model",
        trigger="benchmark",
        started_at="2025-01-01T00:00:00+00:00",
    )
    repository.append_observation(
        run_id=run_id,
        subject_kind="model",
        subject_id=subject_id,
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

    historical = client.get(
        "/api/v1/admin/model-providers/model-matrix",
        params={"run_id": run_id},
    )
    historical_model = next(
        item
        for item in historical.json()["models"]
        if item["display_name"] == "Model A"
    )
    historical_cell = next(
        item
        for item in historical_model["connections"]
        if item["connection_id"] == connection_id
    )
    assert historical_cell["latency_ms"] == 42.0
    assert historical_cell["latency_class"] == "fast"


def test_refresh_uses_official_remote_then_bundled_fallbacks(
    tmp_path,
    monkeypatch,
) -> None:
    client = _client(tmp_path, monkeypatch)

    official = _create_connection(client, alias="Official", catalog_id="openai_api")
    with (
        patch(
            "infrastructure.models.provider_administration.ProviderModelsAdapter._discover_with_slot",
            return_value=[DiscoveredModel("openai", "official-model")],
        ),
        patch(
            "infrastructure.models.provider_administration.fetch_remote_models",
            side_effect=AssertionError("remote adapter must not run"),
        ),
    ):
        refreshed = client.post(
            f"/api/v1/admin/model-providers/connections/{official['connection_id']}/models/refresh"
        )
    assert refreshed.status_code == 200
    assert refreshed.json()["status"] == "updated"
    assert {item["source"] for item in refreshed.json()["models"]} == {
        "manual",
        "official",
    }

    remote = _create_connection(client, alias="Remote", catalog_id="openai_api")
    with (
        patch(
            "infrastructure.models.provider_administration.ProviderModelsAdapter._discover_with_slot",
            side_effect=RuntimeError("official unavailable"),
        ),
        patch(
            "infrastructure.models.provider_administration.fetch_remote_models",
            return_value=("remote-model",),
        ),
    ):
        refreshed = client.post(
            f"/api/v1/admin/model-providers/connections/{remote['connection_id']}/models/refresh"
        )
    assert refreshed.json()["status"] == "remote_catalog"
    assert {item["source"] for item in refreshed.json()["models"]} == {
        "manual",
        "remote_catalog",
    }

    bundled = _create_connection(client, alias="Bundled", catalog_id="openai_api")
    with (
        patch(
            "infrastructure.models.provider_administration.ProviderModelsAdapter._discover_with_slot",
            side_effect=RuntimeError("official unavailable"),
        ),
        patch(
            "infrastructure.models.provider_administration.fetch_remote_models",
            return_value=(),
        ),
    ):
        refreshed = client.post(
            f"/api/v1/admin/model-providers/connections/{bundled['connection_id']}/models/refresh"
        )
    assert refreshed.json()["status"] == "bundled_catalog"
    sources = {item["source"] for item in refreshed.json()["models"]}
    assert "manual" in sources
    assert "bundled_catalog" in sources


def test_benchmark_and_validate_all_project_named_results(
    tmp_path,
    monkeypatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    created = _create_connection(client, alias="Checks")
    connection_id = str(created["connection_id"])

    with patch(
        "infrastructure.models.provider_administration.bounded_benchmark",
        new=AsyncMock(
            return_value={
                "status": "passed",
                "latency_ms": 12.0,
                "latency_class": "fast",
                "error": None,
            }
        ),
    ):
        benchmark = client.post(
            "/api/v1/admin/model-providers/model-benchmarks",
            json={
                "combinations": [
                    {"connection_id": connection_id, "model_id": "model-a"}
                ]
            },
        )

    assert benchmark.status_code == 200
    assert benchmark.json()["status"] == "complete"
    assert benchmark.json()["results"][0]["latency_ms"] == 12.0

    with patch(
        "infrastructure.models.provider_administration.validate_connection",
        new=AsyncMock(
            return_value={
                "status": "passed",
                "checked_at": "2026-08-10T00:00:00+00:00",
                "model_results": [
                    {
                        "model_id": "model-a",
                        "status": "passed",
                        "checked_at": "2026-08-10T00:00:00+00:00",
                    }
                ],
            }
        ),
    ):
        validation = client.post("/api/v1/admin/model-providers/model-validations")

    assert validation.status_code == 200
    assert validation.json()["status"] == "complete"
    assert {item["subject"] for item in validation.json()["results"]} >= {
        f"provider:{connection_id}",
        f"model:{connection_id}/model-a",
    }


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
