from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.features.configuration import (
    ProviderPortError,
    StoredProviderConnection,
    StoredProviderModel,
)
from infrastructure.models.provider_administration import ProviderModelsAdapter


def test_provider_adapter_keeps_secret_out_of_connection_fact(tmp_path) -> None:
    provider_path = tmp_path / "providers.yaml"
    secret_path = tmp_path / "auth.env"
    adapter = ProviderModelsAdapter(provider_path, secret_path)

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
    adapter = ProviderModelsAdapter(
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
    adapter = ProviderModelsAdapter(
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
    adapter = ProviderModelsAdapter(
        tmp_path / "providers.yaml",
        tmp_path / "auth.env",
    )
    run = _RunSpy()

    async def disconnected() -> bool:
        return True

    with patch(
        "infrastructure.models.provider_administration.ReportRepository",
        return_value=run,
    ):
        result = asyncio.run(
            adapter.validate_all((_validation_connection(),), disconnected)
        )

    assert result.status == "partial"
    assert run.finished_status == "partial"


def test_validate_all_finalizes_partial_run_after_cancellation(tmp_path) -> None:
    adapter = ProviderModelsAdapter(
        tmp_path / "providers.yaml",
        tmp_path / "auth.env",
    )
    run = _RunSpy()

    async def connected() -> bool:
        return False

    with (
        patch(
            "infrastructure.models.provider_administration.ReportRepository",
            return_value=run,
        ),
        patch(
            "infrastructure.models.provider_administration.validate_connection",
            new=AsyncMock(side_effect=asyncio.CancelledError),
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        asyncio.run(adapter.validate_all((_validation_connection(),), connected))

    assert run.finished_status == "partial"


def test_validate_all_finalizes_failed_run_after_error(tmp_path) -> None:
    adapter = ProviderModelsAdapter(
        tmp_path / "providers.yaml",
        tmp_path / "auth.env",
    )
    run = _RunSpy()

    async def connected() -> bool:
        return False

    with (
        patch(
            "infrastructure.models.provider_administration.ReportRepository",
            return_value=run,
        ),
        patch(
            "infrastructure.models.provider_administration.validate_connection",
            new=AsyncMock(side_effect=RuntimeError("connection broken")),
        ),
        pytest.raises(ProviderPortError, match="Provider validation failed"),
    ):
        asyncio.run(adapter.validate_all((_validation_connection(),), connected))

    assert run.finished_status == "failed"
