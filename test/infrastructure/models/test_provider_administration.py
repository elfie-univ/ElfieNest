from __future__ import annotations

import asyncio
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
from infrastructure.persistence.model_catalog import load_model_identities
from test.support.provider import provider_models_adapter


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
    assert custom.context_window_tokens is None
    assert custom.supports_vision is None


def test_volcengine_refresh_uses_coding_plan_catalog_and_drops_discovered_models(
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
            ),
        ),
        None,
    )

    with patch.object(
        type(adapter),
        "_discover_with_slot",
        side_effect=AssertionError("Coding Plan must not call /models"),
    ):
        refreshed = asyncio.run(adapter.refresh_models(connection))

    assert refreshed.status == "bundled_catalog"
    assert refreshed.message == (
        "火山引擎 Coding Plan 使用配置文件中的官方 Model Name 清单，"
        "未使用 /models（通用模型列表与套餐不匹配）"
    )
    assert [model.model_id for model in refreshed.models] == [
        "doubao-seed-2.0-lite",
        "glm-5.2",
        "kimi-k2.7-code",
        "deepseek-v4-pro",
        "minimax-m3",
        "doubao-seed-2.1-turbo",
        "deepseek-v4-flash",
        "glm-5.3",
    ]
    assert refreshed.persisted_models is not None
    stale = next(
        item
        for item in refreshed.persisted_models
        if item.model_id == "wrong-model-from-generic-models-endpoint"
    )
    assert stale.discovery_state == "source_missing"


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
