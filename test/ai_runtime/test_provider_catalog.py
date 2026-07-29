from __future__ import annotations

from pathlib import Path

import yaml

from ai_runtime.providers.catalog import (
    BUNDLED_PROVIDER_CATALOG_PATH,
    load_provider_catalog,
)
from ai_runtime.providers.profiles import BUILTIN_PROFILES


def _provider(
    *,
    name: str,
    api_base: str,
    connection_method: str,
    auth_type: str = "bearer",
    api_mode: str = "chat_completions",
) -> dict:
    env_prefix = name.upper().replace(" ", "_")
    return {
        "name": name,
        "api_base": api_base,
        "auth_type": auth_type,
        "api_mode": api_mode,
        "base_url_env_var": f"{env_prefix}_API_BASE",
        "api_key_env_var": f"{env_prefix}_API_KEY",
        "connection_method": connection_method,
        "oauth_available": False,
        "test_model": "example-model",
        "default_models": {
            "cheap": ["example-model"],
            "deep": ["example-model"],
            "multimodal": ["example-model"],
        },
    }


def _override_document() -> dict:
    return {
        "version": 1,
        "providers": {
            "ollama": _provider(
                name="Ollama",
                api_base="http://localhost:11434",
                connection_method="local",
                auth_type="none",
                api_mode="ollama",
            ),
            "custom_openai": _provider(
                name="Custom OpenAI",
                api_base="http://localhost:8000/v1",
                connection_method="api_key",
            ),
            "new_gateway": _provider(
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
    assert catalog.version == 1
    assert catalog.profiles == BUILTIN_PROFILES
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
    } == set(catalog.profiles)


def test_local_provider_catalog_can_add_supported_provider(tmp_path) -> None:
    override_path = tmp_path / "provider-catalog.yaml"
    override_path.write_text(
        yaml.safe_dump(_override_document(), sort_keys=False),
        encoding="utf-8",
    )

    catalog = load_provider_catalog(override_path)

    assert catalog.source == override_path
    assert catalog.profiles["new_gateway"].api_base == ("https://gateway.example/v1")
    assert catalog.suggested_models("https://gateway.example/v1") == ["gateway-model"]


def test_invalid_local_provider_catalog_falls_back_to_bundled(
    tmp_path,
) -> None:
    override_path = tmp_path / "provider-catalog.yaml"
    override_path.write_text(
        yaml.safe_dump({"version": 999, "providers": {}}),
        encoding="utf-8",
    )

    catalog = load_provider_catalog(override_path)

    assert catalog.source == BUNDLED_PROVIDER_CATALOG_PATH
    assert "openai" in catalog.profiles


def test_provider_catalog_rejects_plaintext_credentials(tmp_path) -> None:
    document = _override_document()
    document["providers"]["new_gateway"]["api_key"] = "must-not-load"
    override_path = tmp_path / "provider-catalog.yaml"
    override_path.write_text(
        yaml.safe_dump(document, sort_keys=False),
        encoding="utf-8",
    )

    catalog = load_provider_catalog(override_path)

    assert catalog.source == BUNDLED_PROVIDER_CATALOG_PATH
    assert "new_gateway" not in catalog.profiles


def test_legacy_provider_views_are_derived_from_catalog() -> None:
    from ai_runtime.config import PROVIDER_RECOMMENDS
    from ai_runtime.setup.runtime_setup import PROVIDER_METADATA

    assert set(PROVIDER_RECOMMENDS) == set(BUILTIN_PROFILES)
    for provider_id, profile in BUILTIN_PROFILES.items():
        recommendation = PROVIDER_RECOMMENDS[provider_id]
        assert recommendation["api_base"] == profile.api_base
        assert recommendation["cheap_models"] == profile.default_models["cheap"]

    for provider_id, metadata in PROVIDER_METADATA.items():
        profile = BUILTIN_PROFILES[provider_id]
        assert metadata["api_base"] == profile.api_base
        assert metadata["test_model"] == profile.test_model
