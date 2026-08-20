from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.features.configuration import (
    ProviderModelInput,
    ProviderPortError,
    StoredProviderConnection,
    StoredProviderModel,
)
from infrastructure.models.provider_records import ProviderModelRecord
from infrastructure.models.providers.discovery import (
    bundled_catalog_models,
    merge_refreshed_models,
)
from infrastructure.models.validation.provider_capability_probes import (
    CapabilityProbeResult,
)
from infrastructure.models.validation.provider_validation import (
    DiscoveredModel,
    ModelDiscoveryResult,
)
from infrastructure.models.validation.serving_food import ServingFoodIndex
from infrastructure.persistence.model_catalog import load_model_identities
from infrastructure.persistence.provider_catalog import load_provider_catalog
from infrastructure.persistence.report_storage import ReportStorageAdapter
from infrastructure.persistence.reports.report_repository import ReportRepository
from test.support.provider import provider_models_adapter


def test_project_connections_reuses_request_level_provider_facts(tmp_path) -> None:
    adapter = provider_models_adapter(
        tmp_path / "providers.yaml",
        tmp_path / "auth.env",
    )
    connections = tuple(
        adapter.create_connection(
            StoredProviderConnection(
                connection_id="",
                catalog_id="custom_openai",
                alias=alias,
                api_base="https://gateway.example/v1",
                api_mode="chat_completions",
                auth_type="bearer",
                credential_ref="",
                models=(
                    StoredProviderModel("model-a", "Model A"),
                    StoredProviderModel("model-b", "Model B"),
                ),
            ),
            None,
        )
        for alias in ("First", "Second")
    )
    serving_index_calls = 0

    def serving_index() -> ServingFoodIndex:
        nonlocal serving_index_calls
        serving_index_calls += 1
        return ServingFoodIndex("test", (), ())

    adapter.set_serving_index(serving_index)
    with patch.object(
        adapter._store,
        "load_connections",
        wraps=adapter._store.load_connections,
    ) as load_connections:
        projections = adapter.project_connections(connections)

    assert load_connections.call_count == 0
    assert serving_index_calls == 1
    assert [item.connection_id for item in projections] == [
        item.connection_id for item in connections
    ]
    assert [tuple(item.model_verifications) for item in projections] == [
        ("model-a", "model-b"),
        ("model-a", "model-b"),
    ]


def test_refresh_keeps_missing_discovered_models_until_two_complete_omissions() -> None:
    existing = (
        ProviderModelRecord(
            "current",
            display_name="Custom current name",
            source="bundled_catalog",
        ),
        ProviderModelRecord(
            "expired",
            available=False,
            source="bundled_catalog",
        ),
        ProviderModelRecord("manual-only", source="manual"),
    )
    refreshed = (ProviderModelRecord("current", source="official"),)

    merged = merge_refreshed_models(existing, refreshed)

    assert [model.endpoint_model_id for model in merged] == [
        "current",
        "expired",
        "manual-only",
    ]
    assert merged[0].available is True
    manual = next(item for item in merged if item.endpoint_model_id == "manual-only")
    missing = next(item for item in merged if item.endpoint_model_id == "expired")
    assert manual.source == "manual"
    assert missing.consecutive_missing == 1
    assert missing.discovery_state == "present"

    second = merge_refreshed_models(
        merged,
        refreshed,
        complete=True,
        observed_at="2026-08-15T00:00:00+00:00",
    )
    missing = next(item for item in second if item.endpoint_model_id == "expired")
    assert missing.consecutive_missing == 2
    assert missing.discovery_state == "source_missing"
    assert missing.available is False


def test_authority_change_hides_old_inventory_but_preserves_serving_endpoint() -> None:
    existing = (
        ProviderModelRecord("old-platform-model", source="official"),
        ProviderModelRecord("serving-model", source="official"),
        ProviderModelRecord("manual-model", source="manual"),
    )

    merged = merge_refreshed_models(
        existing,
        (ProviderModelRecord("new-curated-model", source="official"),),
        complete=True,
        authority_changed=True,
        preserve_model_ids=("serving-model",),
    )

    old = next(
        item for item in merged if item.endpoint_model_id == "old-platform-model"
    )
    serving = next(item for item in merged if item.endpoint_model_id == "serving-model")
    manual = next(item for item in merged if item.endpoint_model_id == "manual-model")
    assert old.discovery_state == "source_missing"
    assert serving.discovery_state == "present"
    assert manual.discovery_state == "present"


def test_bundled_refresh_repairs_legacy_hidden_core_models_without_reenabling_user_choices() -> (
    None
):
    merged = merge_refreshed_models(
        (
            ProviderModelRecord("legacy-core", source="official", hidden=True),
            ProviderModelRecord("current-core", source="bundled_catalog", hidden=True),
            ProviderModelRecord("manual-model", source="manual", hidden=True),
        ),
        (
            ProviderModelRecord("legacy-core", source="bundled_catalog"),
            ProviderModelRecord("current-core", source="bundled_catalog"),
            ProviderModelRecord("manual-model", source="manual"),
        ),
        reset_hidden_for_refreshed=True,
    )

    by_id = {item.endpoint_model_id: item for item in merged}
    assert by_id["legacy-core"].hidden is False
    assert by_id["current-core"].hidden is True
    assert by_id["manual-model"].hidden is True


def test_live_refresh_retains_broad_inventory_as_hidden_other_models(tmp_path) -> None:
    adapter = provider_models_adapter(
        tmp_path / "providers.yaml",
        tmp_path / "auth.env",
    )
    product = adapter.get_product("openai_api")
    assert product is not None
    curated_model = (
        load_provider_catalog().products[product.catalog_id].bundled_models[0]
    )
    connection = adapter.create_connection(
        StoredProviderConnection(
            connection_id="",
            catalog_id=product.catalog_id,
            alias=product.name,
            api_base=product.api_base,
            api_mode=product.api_mode,
            auth_type=product.auth_type,
            credential_ref="",
            models=(
                StoredProviderModel(
                    "old-platform-model",
                    "Old platform model",
                    source="official",
                    consecutive_missing=1,
                ),
            ),
        ),
        None,
    )
    discovery = ModelDiscoveryResult(
        provider=connection.connection_id,
        models=(
            DiscoveredModel(
                connection.connection_id,
                curated_model,
                source="provider_models",
                curated=True,
            ),
            DiscoveredModel(
                connection.connection_id,
                "other-platform-model",
                source="provider_models",
            ),
        ),
        source="provider_models",
        complete=True,
        authoritative=True,
    )

    with patch.object(type(adapter), "_discover_with_slot", return_value=discovery):
        refreshed = asyncio.run(adapter.refresh_models(connection))

    assert [item.model_id for item in refreshed.models if not item.hidden] == [
        curated_model
    ]
    other = next(
        item for item in refreshed.models if item.model_id == "other-platform-model"
    )
    assert other.hidden is True
    assert other.discovery_state == "present"
    assert refreshed.persisted_models is not None
    stale = next(
        item
        for item in refreshed.persisted_models
        if item.model_id == "old-platform-model"
    )
    assert stale.discovery_state == "source_missing"


def test_manual_model_does_not_inherit_capabilities_from_canonical_identity(
    tmp_path,
) -> None:
    adapter = provider_models_adapter(
        tmp_path / "providers.yaml", tmp_path / "auth.env"
    )

    prepared = adapter.prepare_manual_model(
        ProviderModelInput(model_id="xopglm5", display_name="GLM-5")
    )

    assert prepared.canonical_model_id == "zhipu/glm-5"
    assert prepared.supports_tools is None
    assert prepared.supports_vision is None
    assert prepared.supports_reasoning is None


def test_capability_probe_persists_endpoint_specific_evidence(tmp_path) -> None:
    adapter = provider_models_adapter(
        tmp_path / "providers.yaml",
        tmp_path / "auth.env",
    )
    connection = adapter.create_connection(
        StoredProviderConnection(
            connection_id="",
            catalog_id="custom_openai",
            alias="Gateway",
            api_base="https://gateway.example/v1",
            api_mode="chat_completions",
            auth_type="bearer",
            credential_ref="",
            models=(StoredProviderModel("model-a", "Model A"),),
        ),
        None,
    )
    with patch(
        "infrastructure.models.provider_administration.run_capability_probes",
        return_value=(
            CapabilityProbeResult(
                "tools",
                "supported",
                "verified",
                "passed",
                12.0,
            ),
        ),
    ):
        results = asyncio.run(
            adapter.probe_capabilities(
                f"{connection.connection_id}/model-a",
                ("tools",),
            )
        )

    assert results[0].evidence == "verified"
    refreshed = adapter.get_connection(connection.connection_id)
    assert refreshed is not None
    model = refreshed.models[0]
    assert model.supports_tools is True
    assert model.capability_evidence["tools"] == "verified"

    with patch(
        "infrastructure.models.provider_administration.run_capability_probes",
        side_effect=AssertionError("verified capability must not be re-probed"),
    ):
        assert (
            asyncio.run(
                adapter.probe_capabilities(
                    f"{connection.connection_id}/model-a",
                    ("tools",),
                )
            )
            == ()
        )


def test_accepted_capability_evidence_can_be_reprobed_by_explicit_action(
    tmp_path,
) -> None:
    adapter = provider_models_adapter(
        tmp_path / "providers.yaml",
        tmp_path / "auth.env",
    )
    connection = adapter.create_connection(
        StoredProviderConnection(
            connection_id="",
            catalog_id="custom_openai",
            alias="Gateway",
            api_base="https://gateway.example/v1",
            api_mode="chat_completions",
            auth_type="bearer",
            credential_ref="",
            models=(StoredProviderModel("model-a", "Model A"),),
        ),
        None,
    )
    with patch(
        "infrastructure.models.provider_administration.run_capability_probes",
        return_value=(
            CapabilityProbeResult(
                "vision",
                "supported",
                "accepted",
                "passed",
                12.0,
            ),
        ),
    ):
        asyncio.run(
            adapter.probe_capabilities(
                f"{connection.connection_id}/model-a",
                ("vision",),
            )
        )

    with patch(
        "infrastructure.models.provider_administration.run_capability_probes",
        return_value=(),
    ) as probe:
        asyncio.run(
            adapter.probe_capabilities(
                f"{connection.connection_id}/model-a",
                ("vision",),
            )
        )
    probe.assert_called_once()


def test_source_missing_model_is_listed_as_cleanup_candidate_after_retention(
    tmp_path,
) -> None:
    adapter = provider_models_adapter(
        tmp_path / "providers.yaml",
        tmp_path / "auth.env",
    )
    connection = adapter.create_connection(
        StoredProviderConnection(
            connection_id="",
            catalog_id="custom_openai",
            alias="Gateway",
            api_base="https://gateway.example/v1",
            api_mode="chat_completions",
            auth_type="bearer",
            credential_ref="",
            models=(
                StoredProviderModel(
                    "retired-model",
                    "Retired model",
                    source="remote_catalog",
                    discovery_state="source_missing",
                    consecutive_missing=2,
                    last_seen_at="2025-01-01T00:00:00+00:00",
                ),
            ),
        ),
        None,
    )

    candidates = adapter.list_obsolete_models(connection.connection_id)

    assert len(candidates) == 1
    assert candidates[0].eligible is True
    adapter.delete_obsolete_model(connection.connection_id, "retired-model")
    refreshed = adapter.get_connection(connection.connection_id)
    assert refreshed is not None
    assert refreshed.models == ()


def test_recent_production_use_blocks_source_missing_model_cleanup(tmp_path) -> None:
    report_repository = ReportRepository(tmp_path / "reports.sqlite")
    adapter = provider_models_adapter(
        tmp_path / "providers.yaml",
        tmp_path / "auth.env",
        reports=ReportStorageAdapter(report_repository),
    )
    connection = adapter.create_connection(
        StoredProviderConnection(
            connection_id="",
            catalog_id="custom_openai",
            alias="Gateway",
            api_base="https://gateway.example/v1",
            api_mode="chat_completions",
            auth_type="bearer",
            credential_ref="",
            models=(
                StoredProviderModel(
                    "retired-model",
                    "Retired model",
                    source="remote_catalog",
                    discovery_state="source_missing",
                    consecutive_missing=2,
                    last_seen_at="2025-01-01T00:00:00+00:00",
                ),
            ),
        ),
        None,
    )
    run_id = report_repository.start_run(scope="model", trigger="production")
    report_repository.append_observation(
        run_id=run_id,
        subject_kind="model",
        subject_id=f"{connection.connection_id}/retired-model",
        observed_at=datetime.now(timezone.utc).isoformat(),
        status="passed",
        details={"workload_kind": "production"},
    )
    report_repository.finish_run(run_id, status="complete")

    candidates = adapter.list_obsolete_models(connection.connection_id)

    assert len(candidates) == 1
    assert candidates[0].eligible is False
    assert candidates[0].reason == "近 30 天仍有生产使用"
    with pytest.raises(ProviderPortError, match="安全清理条件"):
        adapter.delete_obsolete_model(connection.connection_id, "retired-model")

    retained = adapter.get_connection(connection.connection_id)
    assert retained is not None
    assert [item.model_id for item in retained.models] == ["retired-model"]


def test_bundled_endpoint_metadata_is_not_shared_across_providers() -> None:
    identity_catalog = load_model_identities()
    openai = bundled_catalog_models(
        ("gpt-4o",), provider_id="openai", identity_catalog=identity_catalog
    )[0]
    custom = bundled_catalog_models(
        ("gpt-4o",), provider_id="custom_openai", identity_catalog=identity_catalog
    )[0]

    assert openai.context_window_tokens == 128000
    assert openai.supports_vision is True
    assert openai.capability_evidence["vision"] == "declared"
    assert custom.context_window_tokens is None
    assert custom.supports_vision is None


def test_volcengine_refresh_uses_only_core_models_and_reclassifies_old_inventory(
    tmp_path,
) -> None:
    adapter = provider_models_adapter(
        tmp_path / "providers.yaml",
        tmp_path / "auth.env",
    )
    product = adapter.get_product("volcengine_coding_plan")
    assert product is not None
    connection = adapter.create_connection(
        StoredProviderConnection(
            connection_id="",
            catalog_id=product.catalog_id,
            alias=product.name,
            api_base=product.api_base,
            api_mode=product.api_mode,
            auth_type=product.auth_type,
            credential_ref="",
            models=(
                StoredProviderModel(
                    "wrong-model-from-generic-models-endpoint",
                    "Wrong model",
                    source="official",
                ),
                StoredProviderModel(
                    "deepseek-v4-pro",
                    "DeepSeek V4 Pro",
                    source="official",
                    hidden=True,
                ),
            ),
        ),
        None,
    )

    discovery = ModelDiscoveryResult(
        provider=connection.connection_id,
        models=(
            DiscoveredModel(
                connection.connection_id,
                "deepseek-v4-pro",
                source="bundled_catalog",
                curated=True,
            ),
        ),
        source="bundled_catalog",
        complete=True,
        authoritative=True,
    )
    with patch.object(type(adapter), "_discover_with_slot", return_value=discovery):
        first = asyncio.run(adapter.refresh_models(connection))
        assert first.persisted_models is not None
        stale_after_authority_change = next(
            item
            for item in first.persisted_models
            if item.model_id == "wrong-model-from-generic-models-endpoint"
        )
        assert stale_after_authority_change.discovery_state == "source_missing"
        restored_core = next(
            item
            for item in first.persisted_models
            if item.model_id == "deepseek-v4-pro"
        )
        assert restored_core.hidden is False
        refreshed = asyncio.run(
            adapter.refresh_models(replace(connection, models=first.persisted_models))
        )

    assert refreshed.status == "updated"
    assert [model.model_id for model in refreshed.models] == ["deepseek-v4-pro"]
    assert refreshed.persisted_models is not None
    stale = next(
        item
        for item in refreshed.persisted_models
        if item.model_id == "wrong-model-from-generic-models-endpoint"
    )
    assert stale.discovery_state == "source_missing"


@pytest.mark.parametrize("failure_mode", ("returned_error", "raised_error"))
def test_volcengine_fallback_never_uses_broad_remote_catalog(
    tmp_path, failure_mode
) -> None:
    adapter = provider_models_adapter(
        tmp_path / "providers.yaml",
        tmp_path / "auth.env",
    )
    product = adapter.get_product("volcengine_coding_plan")
    assert product is not None
    connection = adapter.create_connection(
        StoredProviderConnection(
            connection_id="",
            catalog_id=product.catalog_id,
            alias=product.name,
            api_base=product.api_base,
            api_mode=product.api_mode,
            auth_type=product.auth_type,
            credential_ref="",
            models=(),
        ),
        None,
    )
    discovery = ModelDiscoveryResult(
        provider=connection.connection_id,
        models=(),
        source="bundled_catalog",
        complete=False,
        authoritative=False,
        error="adapter unavailable",
    )
    discovery_patch = (
        patch.object(
            type(adapter),
            "_discover_with_slot",
            side_effect=RuntimeError("adapter unavailable"),
        )
        if failure_mode == "raised_error"
        else patch.object(
            type(adapter),
            "_discover_with_slot",
            return_value=discovery,
        )
    )
    with (
        discovery_patch,
        patch(
            "infrastructure.models.provider_administration.remote_catalog_models",
            side_effect=AssertionError(
                "Volcengine must not use the broad remote catalog"
            ),
        ),
    ):
        result = asyncio.run(adapter.refresh_models(connection))

    assert result.status == "bundled_catalog"
    core_model_ids = load_provider_catalog().products[product.catalog_id].bundled_models
    assert [model.model_id for model in result.models] == core_model_ids


def test_provider_adapter_keeps_secret_out_of_connection_fact(tmp_path) -> None:
    provider_path = tmp_path / "providers.yaml"
    secret_path = tmp_path / "auth.env"
    adapter = provider_models_adapter(provider_path, secret_path)

    created = adapter.create_connection(
        StoredProviderConnection(
            connection_id="",
            catalog_id="openai_api",
            alias="Primary",
            api_base="https://api.openai.com/v1",
            api_mode="chat_completions",
            auth_type="bearer",
            credential_ref="",
            models=(StoredProviderModel("gpt-test", "GPT Test"),),
        ),
        "test-secret",
    )

    assert created.connection_id == "openai_api_0001"
    assert created.credential_ref == "ELFIE_PROVIDER_OPENAI_API_0001_API_KEY"
    assert "test-secret" not in provider_path.read_text(encoding="utf-8")
    assert "test-secret" in secret_path.read_text(encoding="utf-8")


def test_provider_adapter_uses_authoritative_catalog_defaults(tmp_path) -> None:
    adapter = provider_models_adapter(
        tmp_path / "providers.yaml",
        tmp_path / "auth.env",
    )

    product = adapter.get_product("ollama")

    assert product is not None
    adapter.ensure_local_connection(product)
    stored = adapter.list_connections()
    assert len(stored) == 1
    assert stored[0].catalog_id == "ollama"
    assert stored[0].api_base == product.api_base


def test_provider_adapter_preserves_stable_connection_counter(tmp_path) -> None:
    adapter = provider_models_adapter(
        tmp_path / "providers.yaml",
        tmp_path / "auth.env",
    )
    draft = StoredProviderConnection(
        connection_id="",
        catalog_id="openai_api",
        alias="Primary",
        api_base="https://api.openai.com/v1",
        api_mode="chat_completions",
        auth_type="bearer",
        credential_ref="",
        models=(),
    )

    first = adapter.create_connection(draft, None)
    assert adapter.delete_connection(first.connection_id) is True
    second = adapter.create_connection(draft, None)

    assert second.connection_id == "openai_api_0002"


def test_capability_probe_records_verified_channel_evidence_without_text_in_report(
    tmp_path,
) -> None:
    adapter = provider_models_adapter(
        tmp_path / "providers.yaml",
        tmp_path / "auth.env",
    )
    connection = adapter.create_connection(
        StoredProviderConnection(
            connection_id="",
            catalog_id="custom_openai",
            alias="Probe",
            api_base="https://gateway.example/v1",
            api_mode="chat_completions",
            auth_type="bearer",
            credential_ref="",
            models=(StoredProviderModel("model-a", "Model A"),),
        ),
        None,
    )

    with patch(
        "infrastructure.models.provider_administration.call_llm_api_with_trace",
        return_value=("", {"tool_call_count": 1}),
    ):
        result = asyncio.run(
            adapter.probe_model_capability(
                f"{connection.connection_id}/model-a",
                "tools",
            )
        )

    assert result.state == "supported"
    assert result.evidence == "verified"
    observations = adapter._reports.observations_for_subject(
        "model", f"{connection.connection_id}/model-a"
    )
    capability = next(
        item
        for item in observations
        if item.details.get("evidence_kind") == "capability"
    )
    assert capability.details["capability_evidence"] == "verified"
    assert "response_text" not in capability.details


class _RunSpy:
    def __init__(self) -> None:
        self.finished_status: str | None = None

    def start_run(self, **_: str) -> str:
        return "run_test"

    def finish_run(self, _: str, *, status: str, finished_at: str) -> None:
        _ = finished_at
        self.finished_status = status


def _validation_connection() -> StoredProviderConnection:
    return StoredProviderConnection(
        connection_id="custom_openai_0001",
        catalog_id="custom_openai",
        alias="Validation",
        api_base="https://gateway.example/v1",
        api_mode="chat_completions",
        auth_type="bearer",
        credential_ref="",
        models=(StoredProviderModel("model-a", "Model A"),),
    )


def test_validate_all_finalizes_partial_run_after_disconnect(tmp_path) -> None:
    adapter = provider_models_adapter(
        tmp_path / "providers.yaml",
        tmp_path / "auth.env",
    )
    run = _RunSpy()

    async def disconnected() -> bool:
        return True

    adapter._reports = run
    with patch(
        "infrastructure.models.provider_administration.validate_connection",
        new=AsyncMock(return_value={"status": "passed", "model_results": []}),
    ):
        result = asyncio.run(
            adapter.validate_all((_validation_connection(),), disconnected)
        )

    assert result.status == "partial"
    assert run.finished_status == "partial"


def test_validate_all_finalizes_partial_run_after_cancellation(tmp_path) -> None:
    adapter = provider_models_adapter(
        tmp_path / "providers.yaml",
        tmp_path / "auth.env",
    )
    run = _RunSpy()

    async def connected() -> bool:
        return False

    adapter._reports = run
    with (
        patch(
            "infrastructure.models.provider_administration.validate_connection",
            new=AsyncMock(side_effect=asyncio.CancelledError),
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        asyncio.run(adapter.validate_all((_validation_connection(),), connected))

    assert run.finished_status == "partial"


def test_validate_all_finalizes_failed_run_after_error(tmp_path) -> None:
    adapter = provider_models_adapter(
        tmp_path / "providers.yaml",
        tmp_path / "auth.env",
    )
    run = _RunSpy()

    async def connected() -> bool:
        return False

    adapter._reports = run
    with (
        patch(
            "infrastructure.models.provider_administration.validate_connection",
            new=AsyncMock(side_effect=RuntimeError("connection broken")),
        ),
        pytest.raises(ProviderPortError, match="Provider validation failed"),
    ):
        asyncio.run(adapter.validate_all((_validation_connection(),), connected))

    assert run.finished_status == "failed"
