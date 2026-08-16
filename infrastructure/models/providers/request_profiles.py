"""Typed semantic request profiles shared by model adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

ApiMode = Literal["ollama", "chat_completions", "anthropic_messages", "codex_responses"]


@dataclass(frozen=True)
class RequestProfile:
    profile_id: str
    version: int
    api_mode: ApiMode
    tools_field: str | None
    vision_encoding: str | None
    reasoning_parameter: str | None


_PROFILES: Mapping[str, RequestProfile] = {
    "openai_chat_v1": RequestProfile(
        "openai_chat_v1",
        1,
        "chat_completions",
        "tools",
        "content_parts",
        "reasoning_effort",
    ),
    "anthropic_messages_v1": RequestProfile(
        "anthropic_messages_v1",
        1,
        "anthropic_messages",
        "tools",
        "content_blocks",
        "thinking",
    ),
    "codex_responses_v1": RequestProfile(
        "codex_responses_v1",
        1,
        "codex_responses",
        "tools",
        "input_content_parts",
        "reasoning",
    ),
    "ollama_chat_v1": RequestProfile(
        "ollama_chat_v1",
        1,
        "ollama",
        "tools",
        "content_parts",
        "think",
    ),
}


def default_request_profile_id(api_mode: str) -> str:
    """Resolve one stable adapter profile from the Provider API mode."""

    mapping = {
        "chat_completions": "openai_chat_v1",
        "anthropic_messages": "anthropic_messages_v1",
        "codex_responses": "codex_responses_v1",
        "ollama": "ollama_chat_v1",
    }
    try:
        return mapping[api_mode]
    except KeyError as error:
        raise ValueError(
            f"未知 API mode，无法选择 Request Profile: {api_mode}"
        ) from error


def get_request_profile(profile_id: str, version: int | None = None) -> RequestProfile:
    try:
        profile = _PROFILES[profile_id]
    except KeyError as error:
        raise ValueError(f"未知 Request Profile: {profile_id}") from error
    if version is not None and version != profile.version:
        raise ValueError(
            f"Request Profile 版本不匹配: {profile_id} v{version}, expected v{profile.version}"
        )
    return profile


__all__ = (
    "RequestProfile",
    "default_request_profile_id",
    "get_request_profile",
)
