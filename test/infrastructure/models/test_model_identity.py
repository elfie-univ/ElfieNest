from pathlib import Path

import pytest

from infrastructure.models.providers.model_identity import (
    ModelIdentityCatalogError,
    match_model_identity,
    parse_model_identities,
)


def test_model_identity_uses_curated_aliases_without_guessing_unknown_models():
    matched = match_model_identity("xopglm5", "GLM-5")
    unknown = match_model_identity("my-local-model-2026", "我的本地模型")

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
