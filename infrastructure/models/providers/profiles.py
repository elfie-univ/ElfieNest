"""Semantic accessors for the versioned Provider metadata catalog."""

from __future__ import annotations

from infrastructure.models.providers.catalog import (
    ProviderCatalog,
    ProviderProfile,
)


def get_profile(
    provider_name: str,
    *,
    catalog: ProviderCatalog,
) -> ProviderProfile | None:
    """Return one Provider profile from the injected authoritative catalog."""
    return catalog.profiles.get(provider_name)


def get_product(
    catalog_id: str,
    *,
    catalog: ProviderCatalog,
) -> ProviderProfile | None:
    """Return one connection product from the injected authoritative catalog."""
    return catalog.products.get(catalog_id)


def get_default_api_mode(
    provider_name: str,
    *,
    catalog: ProviderCatalog,
) -> str:
    """Return the Provider API mode with OpenAI compatibility as fallback."""
    profile = get_profile(provider_name, catalog=catalog)
    return profile.api_mode if profile else "chat_completions"


__all__ = (
    "get_default_api_mode",
    "get_product",
    "get_profile",
)
