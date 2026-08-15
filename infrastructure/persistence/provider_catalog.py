"""Persistence adapter for the bundled and user Provider catalog documents."""

from __future__ import annotations

import logging
from pathlib import Path

from infrastructure.models.providers.catalog import (
    ProviderCatalog,
    ProviderCatalogError,
    parse_provider_catalog,
)
from infrastructure.persistence.configuration.config_store import (
    ConfigStoreError,
    read_yaml_mapping,
)
from infrastructure.persistence.configuration.documents import (
    BundledConfigSource,
    ConfigDocumentId,
)
from infrastructure.persistence.layout.data_home import get_provider_catalog_path

logger = logging.getLogger("infrastructure.persistence.provider_catalog")


def load_provider_catalog(override_path: Path | None = None) -> ProviderCatalog:
    """Load a validated local override or the bundled baseline document."""
    candidate = override_path or get_provider_catalog_path()
    if candidate.exists():
        try:
            return _load_catalog_file(candidate)
        except ProviderCatalogError as exc:
            logger.warning(
                "Ignoring invalid Provider catalog override %s: %s",
                candidate,
                exc,
            )
    loaded = BundledConfigSource().load(ConfigDocumentId.PROVIDER_CATALOG)
    return parse_provider_catalog(loaded.document, loaded.path)


def _load_catalog_file(path: Path) -> ProviderCatalog:
    if not path.is_file():
        raise ProviderCatalogError(f"Provider catalog does not exist: {path}")
    try:
        document = read_yaml_mapping(path)
    except ConfigStoreError as exc:
        raise ProviderCatalogError(str(exc)) from exc
    return parse_provider_catalog(document, path)


__all__ = ("load_provider_catalog",)
