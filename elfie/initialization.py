"""Stable profile assembly for one Elfie facade."""

from __future__ import annotations

import hashlib

from elfie.profile import (
    ElfieProfile,
    SpeciesCatalog,
    create_visual_profile,
    current_species_catalog,
)


def assemble_profile(
    *,
    elfie_id: str | None,
    supplied: ElfieProfile | None,
    catalog: SpeciesCatalog | None = None,
) -> ElfieProfile:
    """Resolve one stable Profile and merge only explicit configuration sources."""
    catalog = catalog or current_species_catalog()
    if supplied is not None:
        supplied.validate(catalog=catalog)
        return supplied
    stable_id = elfie_id or "elfie_default"
    seed = int.from_bytes(
        hashlib.sha256(stable_id.encode("utf-8")).digest()[:8],
        "big",
    )
    return create_visual_profile(
        elfie_id=stable_id,
        display_name=stable_id,
        species_id=catalog.supported_species[0],
        seed=seed,
        height_direction="standard",
        build_direction="standard",
        catalog=catalog,
    )


__all__ = ("assemble_profile",)
