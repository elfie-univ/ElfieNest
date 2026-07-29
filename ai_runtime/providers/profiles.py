"""Compatibility accessors for the versioned Provider metadata catalog."""

from __future__ import annotations

from typing import Dict

from ai_runtime.providers.catalog import (
    ProviderProfile,
    load_provider_catalog,
)

PROVIDER_CATALOG = load_provider_catalog()
BUILTIN_PROFILES: Dict[str, ProviderProfile] = PROVIDER_CATALOG.profiles


def get_profile(provider_name: str) -> ProviderProfile | None:
    """Return one supported Provider profile, or ``None`` when unknown."""
    return BUILTIN_PROFILES.get(provider_name)


def get_default_api_mode(provider_name: str) -> str:
    """Return the Provider API mode with OpenAI compatibility as fallback."""
    profile = get_profile(provider_name)
    return profile.api_mode if profile else "chat_completions"
