"""Packaged immutable Selfhood seed owned by Brain."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from elfie.profile import (
    ELFARIA_CANON,
    ElfieProfile,
    get_species_canon_for_technical_id,
)


def load_packaged_selfhood_seed() -> dict[str, Any]:
    """Load the creation-time Selfhood seed bundled with the Brain owner."""
    path = Path(__file__).with_name("defaults.yaml")
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"默认 Selfhood seed 必须是映射: {path}")
    return dict(raw)


def load_selfhood_seed_for_profile(profile: ElfieProfile) -> dict[str, Any]:
    """Build a Brain seed anchored to an immutable Profile.

    Persisted residents receive this same shape from the workspace Adapter. A
    direct in-memory assembly must not silently fall back to the generic fox
    description, otherwise Profile and Selfhood would disagree about identity.
    The returned mapping is a creation-time copy; Brain owns it after hand-off.
    """
    seed = deepcopy(load_packaged_selfhood_seed())
    species = get_species_canon_for_technical_id(profile.identity.species_id)
    display_name = profile.identity.display_name
    self_description = (
        f"我是 {display_name}，正式物种名是 {species.display_name}；"
        f"我来自 {ELFARIA_CANON.display_name} 的 "
        f"{ELFARIA_CANON.known_region_name}。"
    )
    seed.update(
        {
            "self_description": self_description,
            "species_name": species.display_name,
            "identity_facts": (
                f"正式物种名是 {species.display_name}，{species.earth_shape_label} 只是地球侧形态说明。",
                f"来自 {ELFARIA_CANON.display_name} 的 {ELFARIA_CANON.known_region_name}。",
                ELFARIA_CANON.earth_arrival_statement,
                f"{ELFARIA_CANON.earth_home_name} 是在地球生活的基地和家。",
            ),
            "behavior_anchors": species.earth_first_contact_cues,
            "knowledge_boundaries": ELFARIA_CANON.knowledge_boundaries,
            "norms": (
                "尊重自愿选择，不把猜测说成亲历。",
                "不知道时说明不知道，并在真实接触中学习地球。",
            ),
        }
    )
    metadata = seed.get("metadata")
    if isinstance(metadata, dict):
        metadata["name"] = display_name
        metadata["description"] = self_description
    return seed


__all__ = ("load_packaged_selfhood_seed", "load_selfhood_seed_for_profile")
