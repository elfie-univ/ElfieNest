"""Stable profile and anatomy assembly for one Elfie facade."""

from __future__ import annotations

import hashlib

from elfie.body import BipedAnatomy, QuadrupedAnatomy
from elfie.body.native.anatomy.base import SomaticAnatomy
from elfie.profile import ElfieProfile, create_visual_profile


def assemble_profile(
    *,
    elfie_id: str | None,
    supplied: ElfieProfile | None,
) -> ElfieProfile:
    """Resolve one stable Profile and merge only explicit configuration sources."""
    if supplied is not None:
        supplied.validate()
        return supplied
    stable_id = elfie_id or "elfie_default"
    seed = int.from_bytes(
        hashlib.sha256(stable_id.encode("utf-8")).digest()[:8],
        "big",
    )
    return create_visual_profile(
        elfie_id=stable_id,
        display_name=stable_id,
        species_id="fox",
        seed=seed,
        height_direction="standard",
        build_direction="standard",
    )


def assemble_anatomy(
    profile: ElfieProfile,
) -> tuple[str, SomaticAnatomy]:
    """Resolve the profile-owned morphology without executing action policy."""
    morphology = profile.embodiment.primary_morphology
    if morphology == "quadruped":
        return morphology, QuadrupedAnatomy()
    species_id = profile.identity.species_id
    return morphology, BipedAnatomy(
        gltf_path=f"res://characters/{species_id}/{species_id}.tscn"
    )


__all__ = ("assemble_anatomy", "assemble_profile")
