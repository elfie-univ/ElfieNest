from infrastructure.models.capabilities import (
    canonical_display_name,
    known_capabilities,
    resolve_model_capability_profile,
)


def test_xfyun_kimi_ids_have_canonical_names_and_multimodal_capabilities():
    profile = resolve_model_capability_profile("xopkimik25", "MiniMax-M2.5")

    assert profile is not None
    assert profile.canonical_name == "Kimi-K2.5"
    assert {"text", "reasoning", "vision"} <= profile.capabilities
    assert canonical_display_name("xopkimik25", "wrong") == "Kimi-K2.5"


def test_xfyun_glm_ids_have_reasoning_but_not_vision():
    assert known_capabilities("xopglm5") == frozenset({"text", "reasoning"})
    assert known_capabilities("xopglm51") == frozenset({"text", "reasoning"})


def test_volcengine_glm_47_id_has_reasoning_capability():
    assert known_capabilities("volcengine_coding_plan_0001/glm-4.7") == frozenset(
        {"text", "reasoning"}
    )


def test_minimax_has_a_different_official_xfyun_id():
    profile = resolve_model_capability_profile("xminimaxm25")

    assert profile is not None
    assert profile.canonical_name == "MiniMax-M2.5"


def test_unknown_model_does_not_invent_capabilities():
    assert resolve_model_capability_profile("private-model", "Company Model") is None
