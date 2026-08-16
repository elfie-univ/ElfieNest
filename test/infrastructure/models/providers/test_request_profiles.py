import pytest

from infrastructure.models.inference.llm_api import _resolve_request_profile
from infrastructure.models.providers.request_profiles import (
    default_request_profile_id,
    get_request_profile,
)


def test_api_modes_share_typed_semantic_request_profiles() -> None:
    profile_id = default_request_profile_id("chat_completions")
    profile = get_request_profile(profile_id, 1)

    assert profile.profile_id == "openai_chat_v1"
    assert profile.tools_field == "tools"
    assert profile.reasoning_parameter == "reasoning_effort"


def test_request_profile_version_is_part_of_the_contract() -> None:
    with pytest.raises(ValueError, match="版本不匹配"):
        get_request_profile("ollama_chat_v1", 2)


def test_model_override_selects_one_endpoint_profile() -> None:
    profile = _resolve_request_profile(
        {
            "api_mode": "chat_completions",
            "request_profile_id": "openai_chat_v1",
            "model_profiles": {
                "model-a": {
                    "request_profile_id": "openai_chat_v1",
                    "request_profile_version": 1,
                }
            },
        },
        "model-a",
        "chat_completions",
    )

    assert profile.profile_id == "openai_chat_v1"


def test_mismatched_model_profile_is_rejected() -> None:
    with pytest.raises(ValueError, match="不匹配"):
        _resolve_request_profile(
            {
                "api_mode": "chat_completions",
                "model_profiles": {"model-a": {"request_profile_id": "ollama_chat_v1"}},
            },
            "model-a",
            "chat_completions",
        )
