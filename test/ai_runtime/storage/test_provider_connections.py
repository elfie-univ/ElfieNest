from __future__ import annotations

import yaml

from ai_runtime.storage.provider_connections import (
    ProviderConnection,
    ProviderConnectionStore,
    ProviderModelRecord,
)


def test_connection_store_allocates_readable_stable_ids_without_reuse(tmp_path):
    path = tmp_path / "providers.yaml"
    store = ProviderConnectionStore(path)

    first = store.create(catalog_id="anthropic_api", alias="Anthropic")
    second = store.create(catalog_id="anthropic_api", alias="工作账号")
    store.delete(second.connection_id)
    third = store.create(catalog_id="anthropic_api", alias="个人账号")

    assert first.connection_id == "anthropic_api_0001"
    assert second.connection_id == "anthropic_api_0002"
    assert third.connection_id == "anthropic_api_0003"
    assert store.load().counters["anthropic_api"] == 3


def test_connection_models_keep_endpoint_identity_and_optional_internal_match(tmp_path):
    store = ProviderConnectionStore(tmp_path / "providers.yaml")
    connection = store.create(
        catalog_id="custom_openai",
        alias="私人网关",
        models=(
            ProviderModelRecord(
                endpoint_model_id="my-local-model-2026",
                display_name="我的本地模型",
            ),
            ProviderModelRecord(
                endpoint_model_id="xopglm5",
                display_name="GLM-5",
                canonical_model_id="zhipu/glm-5",
                source="provider_catalog",
                context_window_tokens=204800,
                max_output_tokens=131072,
                supports_tools=True,
                supports_reasoning=True,
            ),
        ),
    )

    restored = store.load().connections[connection.connection_id]

    assert restored.models[0].canonical_model_id is None
    assert restored.models[1].canonical_model_id == "zhipu/glm-5"
    assert restored.models[1].context_window_tokens == 204800


def test_connection_store_migrates_legacy_provider_document_once(tmp_path):
    path = tmp_path / "providers.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "providers": {
                    "openai": {
                        "display_name": "工作 OpenAI",
                        "api_base": "https://api.openai.com/v1",
                        "api_key_env": "OPENAI_API_KEY",
                        "models": [{"id": "gpt-test", "display_name": "GPT Test"}],
                    },
                    "home_gateway": {
                        "display_name": "家庭网关",
                        "api_base": "http://localhost:8000/v1",
                        "api_mode": "chat_completions",
                        "auth_type": "bearer",
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    document = ProviderConnectionStore(path).load()

    assert set(document.connections) == {
        "openai_api_0001",
        "custom_openai_0001",
    }
    assert document.connections["openai_api_0001"].alias == "工作 OpenAI"
    assert document.connections["custom_openai_0001"].legacy_provider_id == (
        "home_gateway"
    )
    persisted = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert persisted["version"] == 2
    assert "providers" not in persisted
    assert path.with_suffix(".yaml.v1.bak").exists()


def test_connection_store_never_persists_plaintext_credentials(tmp_path):
    path = tmp_path / "providers.yaml"
    store = ProviderConnectionStore(path)
    connection = ProviderConnection(
        connection_id="openai_api_0001",
        catalog_id="openai_api",
        alias="OpenAI",
        api_base="https://api.openai.com/v1",
        credential_ref="ELFIE_PROVIDER_OPENAI_API_0001_API_KEY",
    )

    store.replace(connection)

    content = path.read_text(encoding="utf-8")
    assert "api_key:" not in content
    assert "ELFIE_PROVIDER_OPENAI_API_0001_API_KEY" in content
