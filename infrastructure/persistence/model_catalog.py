"""Persistence loaders for the registered model catalog documents."""

from __future__ import annotations

from pathlib import Path

from infrastructure.models.catalog import ModelEntry, parse_model_catalog
from infrastructure.models.providers.model_identity import (
    ModelIdentityCatalog,
    parse_model_identities,
)
from infrastructure.persistence.configuration.documents import (
    BundledConfigSource,
    ConfigDocumentId,
)


def load_model_catalog(root: Path | None = None) -> dict[str, ModelEntry]:
    """Load and validate the registered model catalog document."""
    loaded = BundledConfigSource(root).load(ConfigDocumentId.MODEL_CATALOG)
    return parse_model_catalog(loaded.document, loaded.path)


def load_model_identities(root: Path | None = None) -> ModelIdentityCatalog:
    """Load and validate the registered canonical model identity document."""
    loaded = BundledConfigSource(root).load(ConfigDocumentId.MODEL_CATALOG)
    return parse_model_identities(loaded.document, loaded.path)


__all__ = ("load_model_catalog", "load_model_identities")
