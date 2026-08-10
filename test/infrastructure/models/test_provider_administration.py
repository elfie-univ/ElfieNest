from __future__ import annotations

from app.features.configuration import (
    StoredProviderConnection,
    StoredProviderModel,
)
from infrastructure.models import ProviderModelsAdapter


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
