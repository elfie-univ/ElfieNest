"""Stable profile and anatomy assembly for one Elfie facade."""

from __future__ import annotations

import hashlib

from elfie.body import BipedAnatomy, QuadrupedAnatomy
from elfie.body.native.anatomy.base import SomaticAnatomy
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


def assemble_anatomy(
    profile: ElfieProfile,
) -> tuple[str, SomaticAnatomy]:
    """Resolve physical anatomy from the runtime species package.

    Anatomy is a runtime/body concern, not part of the external Profile.  The
    current validated species packages all use the biped body path; keeping
    this decision here lets a future body catalog evolve without expanding
    Profile into a capability container.
    """
    catalog = current_species_catalog()
    definition = catalog.definition(profile.identity.species_id)
    morphology = "biped"
    if definition.godot_package_id.endswith("-quadruped"):
        morphology = "quadruped"
    if morphology == "quadruped":
        return morphology, QuadrupedAnatomy()
    species_id = profile.identity.species_id
    return morphology, BipedAnatomy(
        gltf_path=f"res://characters/{species_id}/{species_id}.tscn"
    )


__all__ = ("assemble_anatomy", "assemble_profile")
