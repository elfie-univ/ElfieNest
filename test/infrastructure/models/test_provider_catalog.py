from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from infrastructure.models.providers.catalog import (
    ProviderCatalogError,
    parse_provider_catalog,
)
from infrastructure.persistence.configuration.documents import (
    resolve_bundled_config_root,
)
from infrastructure.persistence.provider_catalog import load_provider_catalog


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


def _bundled_provider_catalog_path() -> Path:
    return resolve_bundled_config_root() / "models" / "provider-catalog.yaml"


def test_builtin_provider_profiles_are_loaded_from_versioned_catalog() -> None:
    catalog = load_provider_catalog(Path("/definitely/missing/provider-catalog.yaml"))

    assert catalog.source == _bundled_provider_catalog_path()
    assert catalog.version == 2
    assert catalog.profiles == load_provider_catalog().profiles
    assert catalog.products["openai_api"].legacy_provider_id == "openai"
    assert catalog.products["openai_api"].usage_scope == "general"
    assert catalog.brands["openai"].logo_asset == "brands/openai.svg"
    assert catalog.products["volcengine_coding_plan"].api_base == (
        "https://ark.cn-beijing.volces.com/api/coding/v3"
    )
    assert catalog.products["volcengine_coding_plan"].discovery_strategy == (
        "catalog_only"
    )
    assert catalog.products["volcengine_coding_plan"].bundled_models == [
        "doubao-seed-2.0-lite",
        "glm-5.2",
        "kimi-k2.7-code",
        "deepseek-v4-pro",
        "minimax-m3",
        "doubao-seed-2.1-turbo",
        "deepseek-v4-flash",
        "glm-5.3",
    ]
    assert catalog.products["glm_api"].brand_id == "zhipu"
    assert catalog.products["kimi_api"].brand_id == "moonshot"
    assert catalog.products["minimax_api"].brand_id == "minimax"
    assert {
        "ollama",
        "openai",
        "openai_chatgpt",
        "anthropic",
        "deepseek",
        "gemini",
        "qwen",
        "zhipu",
        "kimi",
        "minimax",
        "xai",
        "mistral",
        "groq",
        "custom_openai",
        "volcengine_coding_plan",
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

    assert catalog.source == _bundled_provider_catalog_path()
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

    assert catalog.source == _bundled_provider_catalog_path()
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

    assert catalog.source == _bundled_provider_catalog_path()
    assert "new_gateway" not in catalog.profiles


def test_provider_catalog_rejects_unknown_nested_fields() -> None:
    document = _override_document()
    document["products"]["example_api"]["unowned"] = True

    with pytest.raises(ProviderCatalogError, match="unknown fields"):
        parse_provider_catalog(document, Path("provider-catalog.yaml"))
