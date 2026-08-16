"""Infrastructure adapter for presentation images in species packages."""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.features.adoption import AdoptionSpeciesImage, AdoptionSpeciesImages
from elfie.profile import SpeciesCatalog

from .documents import resolve_bundled_config_root
from .species import load_species_catalog, species_asset_path


class BundledSpeciesPresentationAdapter:
    """Serve validated PNGs without copying them into the frontend bundle."""

    def __init__(
        self,
        *,
        catalog: SpeciesCatalog | None = None,
        root: Path | None = None,
    ) -> None:
        self._root = resolve_bundled_config_root(root)
        self._catalog = catalog or load_species_catalog(root=self._root)

    def urls(self, species_id: str) -> AdoptionSpeciesImages:
        self._catalog.definition(species_id, adoptable_only=True)
        prefix = f"/api/v1/me/adoption/species/{species_id}/images"
        return AdoptionSpeciesImages(
            headshot_url=f"{prefix}/headshot",
            full_body_url=f"{prefix}/full-body",
        )

    def read(self, species_id: str, image_kind: str) -> AdoptionSpeciesImage:
        definition = self._catalog.definition(species_id, adoptable_only=True)
        path = species_asset_path(self._root, definition, image_kind)
        content = path.read_bytes()
        return AdoptionSpeciesImage(
            content=content,
            media_type="image/png",
            etag=hashlib.sha256(content).hexdigest(),
        )


__all__ = ("BundledSpeciesPresentationAdapter",)
