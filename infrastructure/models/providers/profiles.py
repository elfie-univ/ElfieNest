"""Compatibility accessors for the versioned Provider metadata catalog."""

from __future__ import annotations

from typing import Any, Dict, Mapping

import yaml

from infrastructure.models.providers.catalog import (
    BUNDLED_PROVIDER_CATALOG_PATH,
    ProviderCatalog,
    ProviderProfile,
    parse_provider_catalog,
)


def _bundled_provider_catalog() -> ProviderCatalog:
    with BUNDLED_PROVIDER_CATALOG_PATH.open(encoding="utf-8") as file:
        document: Any = yaml.safe_load(file) or {}
    if not isinstance(document, Mapping):
        raise RuntimeError("bundled Provider catalog must be an object")
    return parse_provider_catalog(document, BUNDLED_PROVIDER_CATALOG_PATH)


PROVIDER_CATALOG = _bundled_provider_catalog()
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
