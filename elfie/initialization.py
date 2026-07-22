"""Stable profile and anatomy assembly for one Elfie facade."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

from elfie.body import BipedAnatomy, QuadrupedAnatomy
from elfie.body.native.anatomy.base import SomaticAnatomy
from elfie.profile import ElfieProfile, ElfieProfileRepository, create_visual_profile


def assemble_profile(
    *,
    config_dir: str | None,
    elfie_id: str | None,
    supplied: ElfieProfile | None,
) -> ElfieProfile:
    """Resolve one stable Profile and merge only explicit configuration sources."""
    if supplied is not None:
        supplied.validate()
        return supplied
    repository = ElfieProfileRepository(_profile_source(config_dir))
    if repository.exists():
        return repository.load()
    sections = repository.load_legacy_sections()
    personality = sections["personality"]
    metadata = personality.get("metadata", {})
    appearance = metadata.get("appearance", {}) if isinstance(metadata, dict) else {}
    if not isinstance(appearance, dict):
        appearance = {}
    species_id = str(appearance.get("species", "fox"))
    if species_id not in ("dog", "fox"):
        species_id = "fox"
    stable_id = elfie_id or "elfie_default"
    seed = int.from_bytes(
        hashlib.sha256(stable_id.encode("utf-8")).digest()[:8],
        "big",
    )
    profile = create_visual_profile(
        elfie_id=stable_id,
        display_name=str(metadata.get("name") or stable_id),
        species_id=species_id,
        seed=seed,
        height_direction=str(appearance.get("height", "standard")),
        build_direction=str(appearance.get("build", "standard")),
    )
    return replace(
        profile,
        personality=personality,
        capabilities=sections["capabilities"],
        system_limits=sections["system_limits"],
    )


def assemble_anatomy(
    profile: ElfieProfile,
    legacy_anatomy_type: str | None,
) -> tuple[str, SomaticAnatomy]:
    """Resolve the configured morphology without executing any action policy."""
    morphology = legacy_anatomy_type or profile.embodiment.primary_morphology
    if morphology == "quadruped":
        return morphology, QuadrupedAnatomy()
    return morphology, BipedAnatomy()


def _profile_source(config_dir: str | None) -> Path:
    if config_dir is not None:
        return Path(config_dir)
    return Path(__file__).resolve().parent / "profile" / "defaults"


__all__ = ("assemble_anatomy", "assemble_profile")
