"""Direct-domain Selfhood identity seed helpers.

Bundled Selfhood defaults are loaded by Infrastructure and injected through
Bootstrap.  This module only keeps the small identity-derived fallback needed
when a domain object is assembled directly without a composition root.
"""

from __future__ import annotations

from typing import Any

from elfie.profile import (
    ELFARIA_CANON,
    ElfieProfile,
    get_species_canon_for_technical_id,
)


def load_selfhood_seed_for_profile(profile: ElfieProfile) -> dict[str, Any]:
    """Build a Brain seed anchored to an immutable Profile.

    Persisted residents receive this same shape from the workspace Adapter. A
    direct in-memory assembly must not silently fall back to the generic fox
    description, otherwise Profile and Selfhood would disagree about identity.
    This fallback deliberately does not contain the product's bundled
    personality or speech catalog.  Bootstrap supplies those values from the
    registered bundled document in production.
    """
    species = get_species_canon_for_technical_id(profile.identity.species_id)
    display_name = profile.identity.display_name
    self_description = (
        f"我是 {display_name}，正式物种名是 {species.display_name}；"
        f"我来自 {ELFARIA_CANON.display_name} 的 "
        f"{ELFARIA_CANON.known_region_name}。"
    )
    return {
        "metadata": {"name": display_name, "description": self_description},
        "big_five": {},
        "speech_style": {"greetings": ("你好，我来啦。",), "verbal_ticks": "呢"},
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


__all__ = ("load_selfhood_seed_for_profile",)
