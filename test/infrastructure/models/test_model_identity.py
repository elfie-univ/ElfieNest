from pathlib import Path

import pytest

from infrastructure.models.providers.model_identity import (
    ModelIdentityCatalogError,
    match_model_identity,
    parse_model_identities,
)
from infrastructure.persistence.model_catalog import load_model_identities


def test_model_identity_uses_curated_aliases_without_guessing_unknown_models():
    catalog = load_model_identities()
    matched = match_model_identity("xopglm5", "GLM-5", catalog=catalog)
    unknown = match_model_identity(
        "my-local-model-2026", "我的本地模型", catalog=catalog
    )

    assert matched is not None
    assert matched.canonical_model_id == "zhipu/glm-5"
    assert matched.context_window_tokens == 204800
    assert unknown is None


def test_model_identity_rejects_unknown_fields() -> None:
    with pytest.raises(ModelIdentityCatalogError, match="未知字段"):
        parse_model_identities(
            {
                "version": 1,
                "models": {
                    "example/model": {
                        "display_name": "Example",
                        "aliases": ["example"],
                        "unexpected": True,
                    }
                },
                "entries": {},
            },
            Path("model-catalog.yaml"),
        )


def test_static_endpoint_declaration_is_scoped_to_provider() -> None:
    catalog = load_model_identities()

    openai = catalog.endpoint_declaration("openai", "gpt-4o")
    other_provider = catalog.endpoint_declaration("custom_openai", "gpt-4o")

    assert openai is not None
    assert openai.context_window_tokens == 128000
    assert openai.supports_vision is True
    assert other_provider is None


def test_static_endpoint_declaration_loads_output_limit_without_using_canonical_defaults() -> (
    None
):
    catalog = parse_model_identities(
        {
            "version": 1,
            "models": {
                "vendor/model": {
                    "display_name": "Vendor Model",
                    "aliases": ["vendor-model"],
                    "max_output_tokens": 999999,
                }
            },
            "entries": {
                "provider/model": {
                    "provider": "provider",
                    "display_name": "Provider Model",
                    "context_window": 32000,
                    "max_output_tokens": 4096,
                    "capabilities": [],
                }
            },
        },
        Path("model-catalog.yaml"),
    )

    declaration = catalog.endpoint_declaration("provider", "model")
    assert declaration is not None
    assert declaration.max_output_tokens == 4096
    assert declaration.supports_vision is None
