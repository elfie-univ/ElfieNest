from __future__ import annotations

from pathlib import Path

import yaml

from infrastructure.models.providers.catalog import (
    BUNDLED_PROVIDER_CATALOG_PATH,
    load_provider_catalog,
)
from infrastructure.models.providers.profiles import BUILTIN_PROFILES


def _provider(
    *,
    brand_id: str,
    legacy_provider_id: str,
    name: str,
    api_base: str,
    connection_method: str,
    auth_type: str = "bearer",
    api_mode: str = "chat_completions",
) -> dict:
    env_prefix = name.upper().replace(" ", "_")
    return {
        "brand_id": brand_id,
        "legacy_provider_id": legacy_provider_id,
        "name": name,
        "api_base": api_base,
        "auth_type": auth_type,
        "api_mode": api_mode,
        "base_url_env_var": f"{env_prefix}_API_BASE",
        "api_key_env_var": f"{env_prefix}_API_KEY",
        "connection_method": connection_method,
        "usage_scope": "local" if connection_method == "local" else "general",
        "discovery_strategy": (
            "ollama" if connection_method == "local" else "standard_models"
        ),
        "oauth_available": False,
        "test_model": "example-model",
        "bundled_models": ["example-model"],
    }


def _override_document() -> dict:
    return {
        "version": 2,
        "brands": {
            "ollama": {"name": "Ollama", "logo_asset": "brands/ollama.svg"},
            "custom": {"name": "Custom", "logo_asset": ""},
            "example": {"name": "Example", "logo_asset": "brands/example.svg"},
        },
        "products": {
            "ollama": _provider(
                brand_id="ollama",
                legacy_provider_id="ollama",
                name="Ollama",
                api_base="http://localhost:11434",
                connection_method="local",
                auth_type="none",
                api_mode="ollama",
            ),
            "custom_openai": _provider(
                brand_id="custom",
                legacy_provider_id="custom_openai",
                name="Custom OpenAI",
                api_base="http://localhost:8000/v1",
                connection_method="api_key",
            ),
            "example_api": _provider(
                brand_id="example",
                legacy_provider_id="new_gateway",
                name="New Gateway",
                api_base="https://gateway.example/v1",
                connection_method="api_key",
            ),
        },
        "endpoint_model_hints": [
            {
                "api_base_contains": "gateway.example",
                "models": ["gateway-model"],
            }
        ],
    }


def test_builtin_provider_profiles_are_loaded_from_versioned_catalog() -> None:
    catalog = load_provider_catalog(Path("/definitely/missing/provider-catalog.yaml"))

    assert catalog.source == BUNDLED_PROVIDER_CATALOG_PATH
    assert catalog.version == 2
    assert catalog.profiles == BUILTIN_PROFILES
    assert catalog.products["openai_api"].legacy_provider_id == "openai"
    assert catalog.products["openai_api"].usage_scope == "general"
    assert catalog.brands["openai"].logo_asset == "brands/openai.svg"
    assert catalog.products["jdcloud_coding_plan"].api_base == (
        "https://modelservice.jdcloud.com/coding/openai/v1"
    )
    assert catalog.products["jdcloud_coding_plan"].bundled_models == [
        "DeepSeek-V3.2",
        "GLM-5",
        "GLM-4.7",
        "MiniMax-M2.5",
        "Kimi-K2.5",
        "Kimi-K2-Turbo",
        "Qwen3-Coder",
    ]
    assert {
        "ollama",
        "openai",
        "anthropic",
        "deepseek",
        "gemini",
        "qwen",
        "xai",
        "mistral",
        "groq",
        "custom_openai",
        "jdcloud_coding_plan",
    } == set(catalog.profiles)


def test_local_provider_catalog_can_add_supported_provider(tmp_path) -> None:
    override_path = tmp_path / "provider-catalog.yaml"
    override_path.write_text(
        yaml.safe_dump(_override_document(), sort_keys=False),
        encoding="utf-8",
    )

    catalog = load_provider_catalog(override_path)

    assert catalog.source == override_path
    assert catalog.products["example_api"].api_base == ("https://gateway.example/v1")
    assert catalog.profiles["new_gateway"].catalog_id == "example_api"
    assert catalog.suggested_models("https://gateway.example/v1") == ["gateway-model"]


def test_invalid_local_provider_catalog_falls_back_to_bundled(
    tmp_path,
) -> None:
    override_path = tmp_path / "provider-catalog.yaml"
    override_path.write_text(
        yaml.safe_dump({"version": 999, "products": {}}),
        encoding="utf-8",
    )

    catalog = load_provider_catalog(override_path)

    assert catalog.source == BUNDLED_PROVIDER_CATALOG_PATH
    assert "openai" in catalog.profiles


def test_provider_catalog_rejects_plaintext_credentials(tmp_path) -> None:
    document = _override_document()
    document["products"]["example_api"]["api_key"] = "must-not-load"
    override_path = tmp_path / "provider-catalog.yaml"
    override_path.write_text(
        yaml.safe_dump(document, sort_keys=False),
        encoding="utf-8",
    )

    catalog = load_provider_catalog(override_path)

    assert catalog.source == BUNDLED_PROVIDER_CATALOG_PATH
    assert "new_gateway" not in catalog.profiles


def test_provider_catalog_rejects_grouped_bundled_models(tmp_path) -> None:
    document = _override_document()
    document["products"]["example_api"]["bundled_models"] = {
        "legacy": ["example-model"]
    }
    override_path = tmp_path / "provider-catalog.yaml"
    override_path.write_text(
        yaml.safe_dump(document, sort_keys=False),
        encoding="utf-8",
    )

    catalog = load_provider_catalog(override_path)

    assert catalog.source == BUNDLED_PROVIDER_CATALOG_PATH
    assert "new_gateway" not in catalog.profiles


def test_setup_provider_metadata_is_derived_from_catalog() -> None:
    from ai_runtime.setup.runtime_setup import PROVIDER_METADATA

    for provider_id, metadata in PROVIDER_METADATA.items():
        profile = BUILTIN_PROFILES[provider_id]
        assert metadata["api_base"] == profile.api_base
        assert metadata["test_model"] == profile.test_model
