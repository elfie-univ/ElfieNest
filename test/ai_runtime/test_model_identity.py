from ai_runtime.providers.model_identity import match_model_identity


def test_model_identity_uses_curated_aliases_without_guessing_unknown_models():
    matched = match_model_identity("xopglm5", "GLM-5")
    unknown = match_model_identity("my-local-model-2026", "我的本地模型")

    assert matched is not None
    assert matched.canonical_model_id == "zhipu/glm-5"
    assert matched.context_window_tokens == 204800
    assert unknown is None
