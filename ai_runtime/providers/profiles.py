"""Compatibility accessors for the versioned Provider metadata catalog."""

from __future__ import annotations

from typing import Dict

from ai_runtime.providers.catalog import (
    ProviderProfile,
    load_provider_catalog,
)

PROVIDER_CATALOG = load_provider_catalog()
BUILTIN_PROFILES: Dict[str, ProviderProfile] = PROVIDER_CATALOG.profiles
BUILTIN_PRODUCTS: Dict[str, ProviderProfile] = PROVIDER_CATALOG.products


def get_profile(provider_name: str) -> ProviderProfile | None:
    """Return one supported Provider profile, or ``None`` when unknown."""
    return BUILTIN_PROFILES.get(provider_name)


def get_product(catalog_id: str) -> ProviderProfile | None:
    """Return one connection product by its stable catalog ID."""
    return BUILTIN_PRODUCTS.get(catalog_id)


def get_catalog_id(provider_name: str) -> str | None:
    """Resolve one legacy Provider ID to its stable product catalog ID."""
    profile = get_profile(provider_name)
    return profile.catalog_id if profile else None


def get_default_api_mode(provider_name: str) -> str:
    """Return the Provider API mode with OpenAI compatibility as fallback."""
    profile = get_profile(provider_name)
    return profile.api_mode if profile else "chat_completions"
