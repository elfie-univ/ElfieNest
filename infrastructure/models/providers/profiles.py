"""Semantic accessors for the versioned Provider metadata catalog."""

from __future__ import annotations

from pathlib import Path

from infrastructure.models.providers.catalog import (
    ProviderCatalog,
    parse_provider_catalog,
)
from infrastructure.persistence.configuration.documents import (
    BundledConfigSource,
    ConfigDocumentId,
)


def load_bundled_provider_catalog(root: Path | None = None) -> ProviderCatalog:
    """Load the validated bundled catalog from the registered config root."""
    loaded = BundledConfigSource(root).load(ConfigDocumentId.PROVIDER_CATALOG)
    return parse_provider_catalog(loaded.document, loaded.path)


def get_profile(
    provider_name: str,
    *,
    catalog: ProviderCatalog | None = None,
):
    """Return one supported Provider profile, or ``None`` when unknown."""
    return (catalog or load_bundled_provider_catalog()).profiles.get(provider_name)


def get_product(
    catalog_id: str,
    *,
    catalog: ProviderCatalog | None = None,
):
    """Return one connection product by its stable catalog ID."""
    return (catalog or load_bundled_provider_catalog()).products.get(catalog_id)


def get_default_api_mode(
    provider_name: str,
    *,
    catalog: ProviderCatalog | None = None,
) -> str:
    """Return the Provider API mode with OpenAI compatibility as fallback."""
    profile = get_profile(provider_name, catalog=catalog)
    return profile.api_mode if profile else "chat_completions"


__all__ = (
    "get_default_api_mode",
    "get_product",
    "get_profile",
    "load_bundled_provider_catalog",
)
