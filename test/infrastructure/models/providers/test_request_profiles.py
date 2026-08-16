import pytest

from infrastructure.models.inference.llm_api import (
    _adapt_messages,
    _adapt_request_options,
    _resolve_request_profile,
)
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


def test_semantic_tool_and_image_options_use_the_anthropic_wire_shape() -> None:
    profile = get_request_profile("anthropic_messages_v1", 1)
    options = _adapt_request_options(
        {
            "tool_definitions": [
                {
                    "type": "function",
                    "function": {
                        "name": "noop",
                        "description": "No-op",
                        "parameters": {"type": "object"},
                    },
                }
            ],
            "reasoning_mode": "medium",
        },
        profile,
    )
    messages = _adapt_messages(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64,AAAA",
                        },
                    },
                ],
            }
        ],
        profile,
    )

    assert options is not None
    assert options["tools"][0]["input_schema"] == {"type": "object"}
    assert options["thinking"]["type"] == "enabled"
    assert messages[0]["content"][1] == {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": "AAAA",
        },
    }
