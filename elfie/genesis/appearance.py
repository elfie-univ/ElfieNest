"""Appearance proposal and distance helpers for Genesis."""

from __future__ import annotations

import hashlib
import random
from dataclasses import replace
from typing import Mapping, cast

from elfie.profile import (
    AppearanceGenerator,
    AppearanceGenome,
    SpeciesCatalog,
    get_species_definition,
)

from .contracts import CandidateSignature, GenesisAppearanceIntent
from .personality import clamp


def generate_appearance(
    *,
    seed: int,
    species_id: str,
    intent: GenesisAppearanceIntent,
    role: str,
    rng: random.Random,
    life_stage: str,
    age_months: int,
    gender: str,
    variant_index: int | None = None,
    catalog: SpeciesCatalog | None = None,
) -> AppearanceGenome:
    height = {"small": "short", "tall": "tall"}.get(intent.stature)
    build = {"slim": "slim", "round": "plump"}.get(intent.build)
    if height is None:
        height = rng.choice(("short", "standard", "tall"))
    if build is None:
        build = rng.choice(("slim", "standard", "plump"))
    if role == "appearance_anchor":
        height = {"small": "short", "standard": "standard", "tall": "tall"}.get(
            intent.stature, height
        )
        build = {"slim": "slim", "standard": "standard", "round": "plump"}.get(
            intent.build, build
        )
    elif role == "discovery_variant":
        height = rng.choice(("short", "standard", "tall"))
        build = rng.choice(("slim", "standard", "plump"))
    genome = AppearanceGenerator(seed, catalog=catalog).generate(
        species_id=species_id,
        height_direction=height,
        build_direction=build,
        overrides=_overrides(
            species_id,
            intent,
            role,
            rng,
            variant_index=variant_index,
            catalog=catalog,
        ),
        variant_index=variant_index,
    )
    return _apply_creation_context(
        genome,
        species_id=species_id,
        life_stage=life_stage,
        age_months=age_months,
        gender=gender,
        catalog=catalog,
    )


def signature(genome: AppearanceGenome) -> tuple[float, ...]:
    coat = genome.coat
    categories = (
        coat.palette_id,
        coat.primary_color_id or coat.palette_id,
        coat.secondary_color_id or coat.palette_id,
        coat.accent_color_id or coat.secondary_color_id or coat.palette_id,
        coat.pattern_id,
        coat.pattern_layout_id or coat.pattern_id,
        coat.marking_id,
        coat.marking_placement,
        coat.region_recipe_id,
        *(accent.region_id for accent in coat.region_accents),
        *(accent.color_id for accent in coat.region_accents),
        coat.eye_color_id,
    )
    category_values = tuple(
        int.from_bytes(
            hashlib.blake2b(value.encode("utf-8"), digest_size=2).digest(), "big"
        )
        / 65535.0
        for value in categories
    )
    return (
        genome.macro.stature_z / 2.0,
        genome.macro.frame_size_z / 2.0,
        genome.macro.body_fat_z / 2.0,
        genome.macro.muscularity_z / 2.0,
        genome.face.cheek_fullness_bias,
        genome.face.muzzle_length_bias,
        genome.face.eye_size_bias,
        genome.appendages.ear_size_bias,
        genome.appendages.tail_length_bias,
        genome.coat.pattern_contrast_bias,
        genome.coat.marking_scale,
        genome.coat.marking_intensity,
        *category_values,
    )


def visible_key(genome: AppearanceGenome) -> tuple[str, ...]:
    """Return the deterministic visible appearance identity used for de-duplication."""
    coat = genome.coat
    return (
        coat.primary_color_id or coat.palette_id,
        coat.secondary_color_id or coat.primary_color_id or coat.palette_id,
        coat.accent_color_id
        or coat.secondary_color_id
        or coat.primary_color_id
        or coat.palette_id,
        coat.face_mask_color_id
        or coat.secondary_color_id
        or coat.primary_color_id
        or coat.palette_id,
        coat.pattern_id,
        coat.pattern_layout_id or coat.pattern_id,
        coat.marking_id,
        coat.marking_placement,
        coat.region_recipe_id,
        ";".join(
            f"{accent.region_id}:{accent.color_id}:{accent.grade_id}"
            for accent in coat.region_accents
        ),
        _bucket(genome.macro.stature_z),
        _bucket(genome.macro.body_fat_z),
        _bucket(genome.appendages.ear_size_bias),
        _bucket(genome.appendages.tail_length_bias),
    )


def appearance_fit(genome: AppearanceGenome, intent: GenesisAppearanceIntent) -> float:
    values = {
        "stature": genome.macro.stature_z / 2.0,
        "build": genome.macro.body_fat_z / 2.0,
        "face": genome.face.cheek_fullness_bias,
        "signature": min(
            1.0,
            0.12 * len(genome.coat.region_accents)
            + (0.55 if genome.coat.marking_id != "none" else 0.0),
        ),
    }
    targets = {
        "stature": {"small": -0.55, "standard": 0.0, "tall": 0.55, "any": 0.0},
        "build": {"slim": -0.55, "standard": 0.0, "round": 0.55, "any": 0.0},
        "face": {"soft": 0.55, "balanced": 0.0, "defined": -0.55, "any": 0.0},
        "signature": {"warm": 0.35, "marked": 0.65, "ears": 0.45, "any": 0.0},
    }
    weights = dict.fromkeys(values, 0.20)
    weights[intent.priority] = 0.40
    distance = sum(
        weights[key] * abs(values[key] - targets[key][getattr(intent, key)])
        for key in values
    )
    return clamp(1.0 - distance, 0.0, 1.0)


def distance(left: CandidateSignature, right: CandidateSignature) -> float:
    personality = sum(
        abs(a - b) for a, b in zip(left.personality, right.personality)
    ) / len(left.personality)
    appearance = sum(
        abs(a - b) for a, b in zip(left.appearance, right.appearance)
    ) / len(left.appearance)
    return 0.55 * personality + 0.45 * appearance


def _overrides(
    species_id: str,
    intent: GenesisAppearanceIntent,
    role: str,
    rng: random.Random,
    *,
    variant_index: int | None = None,
    catalog: SpeciesCatalog | None = None,
) -> dict[str, object]:
    overrides: dict[str, object] = {}
    if intent.face == "soft":
        overrides["face"] = {
            "cheek_fullness_bias": 0.45,
            "lower_face_fullness_bias": 0.30,
        }
    elif intent.face == "defined":
        overrides["face"] = {
            "cheek_fullness_bias": -0.45,
            "lower_face_fullness_bias": -0.30,
        }
    if role == "discovery_variant" and intent.face == "any":
        overrides["face"] = {
            "cheek_fullness_bias": rng.uniform(-0.65, 0.65),
            "muzzle_length_bias": rng.uniform(-0.55, 0.55),
        }
    if intent.signature == "warm" and variant_index is None:
        species = (
            catalog.definition(species_id, adoptable_only=True)
            if catalog is not None
            else get_species_definition(species_id, adoptable_only=True)
        )
        preferences = (
            species.genesis.appearance_preferences
            if species.genesis is not None
            else {}
        )
        preferred = tuple(
            option
            for option in preferences.get("warm", ())
            if option in species.appearance.palettes
        )
        palettes = preferred or species.appearance.palettes
        cast(dict[str, object], overrides.setdefault("coat", {}))["palette_id"] = (
            rng.choice(palettes)
        )
    elif intent.signature == "marked":
        species = (
            catalog.definition(species_id, adoptable_only=True)
            if catalog is not None
            else get_species_definition(species_id, adoptable_only=True)
        )
        preferences = (
            species.genesis.appearance_preferences
            if species.genesis is not None
            else {}
        )
        preferred = tuple(
            option
            for option in preferences.get("marked", ())
            if option in species.appearance.markings and option != "none"
        )
        markings = preferred or tuple(
            option for option in species.appearance.markings if option != "none"
        )
        marking_id = rng.choice(markings) if markings else "none"
        marking_rule = species.appearance.marking_rules.get(marking_id)
        placements = tuple(
            item
            for item in (marking_rule.placements if marking_rule else ())
            if item != "none"
        )
        cast(dict[str, object], overrides.setdefault("coat", {})).update(
            {
                "pattern_id": species.appearance.patterns[0],
                "marking_id": marking_id,
                "marking_placement": rng.choice(placements) if placements else "none",
                "pattern_contrast_bias": 0.0,
            }
        )
    elif intent.signature == "ears":
        overrides["appendages"] = {
            "ear_size_bias": rng.uniform(0.35, 0.80),
            "ear_tilt_bias": rng.uniform(-0.55, 0.55),
        }
    return overrides


def _bucket(value: float) -> str:
    if value <= -0.45:
        return "low"
    if value >= 0.45:
        return "high"
    return "mid"


def _apply_creation_context(
    genome: AppearanceGenome,
    *,
    species_id: str,
    life_stage: str,
    age_months: int,
    gender: str,
    catalog: SpeciesCatalog | None,
) -> AppearanceGenome:
    """Apply continuous growth and one weak adult sex prior to geometry only."""
    definition = (
        catalog.definition(species_id, adoptable_only=True)
        if catalog is not None
        else get_species_definition(species_id, adoptable_only=True)
    )
    if definition.genesis is None:
        return genome
    ranges = definition.genesis.stage_ranges
    growth = _growth_progress(age_months, ranges)
    juvenile = 1.0 - growth
    elder_minimum, elder_maximum = ranges["elder"]
    elder_progress = (
        clamp(
            (age_months - elder_minimum)
            / max(float(elder_maximum - elder_minimum), 1.0),
            0.0,
            1.0,
        )
        if life_stage == "elder"
        else 0.0
    )
    sex_direction = 1.0 if gender == "male" else -1.0 if gender == "female" else 0.0
    # +/-0.28 z maps to roughly +/-2.5% at the accepted 0.82-1.18 scale.
    sex_height_bias = 0.28 * sex_direction * (0.35 + 0.65 * growth)
    stature_z = _context_value(
        0.78 * genome.macro.stature_z
        - 1.30 * juvenile
        - 0.10 * elder_progress
        + sex_height_bias,
        -2.0,
        2.0,
    )

    proportions = genome.proportions
    contextual_proportions = replace(
        proportions,
        head_torso_bias=_context_value(
            proportions.head_torso_bias + 0.58 * juvenile, -1.0, 1.0
        ),
        neck_torso_bias=_context_value(
            proportions.neck_torso_bias - 0.12 * juvenile, -1.0, 1.0
        ),
        arm_torso_bias=_context_value(
            proportions.arm_torso_bias - 0.38 * juvenile, -1.0, 1.0
        ),
        leg_torso_bias=_context_value(
            proportions.leg_torso_bias - 0.48 * juvenile, -1.0, 1.0
        ),
        hand_arm_bias=_context_value(
            proportions.hand_arm_bias + 0.12 * juvenile, -1.0, 1.0
        ),
        paw_leg_bias=_context_value(
            proportions.paw_leg_bias + 0.16 * juvenile, -1.0, 1.0
        ),
    )
    contextual_face = replace(
        genome.face,
        eye_size_bias=_context_value(
            genome.face.eye_size_bias + 0.20 * juvenile, -1.0, 1.0
        ),
    )
    contextual_appendages = replace(
        genome.appendages,
        tail_length_bias=_context_value(
            genome.appendages.tail_length_bias - 0.16 * juvenile, -1.0, 1.0
        ),
    )
    return replace(
        genome,
        macro=replace(genome.macro, stature_z=stature_z),
        proportions=contextual_proportions,
        face=contextual_face,
        appendages=contextual_appendages,
    )


def _growth_progress(
    age_months: int, stage_ranges: Mapping[str, tuple[int, int]]
) -> float:
    youth_minimum = stage_ranges["youth"][0]
    young_adult_minimum = stage_ranges["young_adult"][0]
    mature_minimum = stage_ranges["mature"][0]
    if age_months < young_adult_minimum:
        return 0.65 * clamp(
            (age_months - youth_minimum)
            / max(float(young_adult_minimum - youth_minimum), 1.0),
            0.0,
            1.0,
        )
    if age_months < mature_minimum:
        return 0.65 + 0.35 * clamp(
            (age_months - young_adult_minimum)
            / max(float(mature_minimum - young_adult_minimum), 1.0),
            0.0,
            1.0,
        )
    return 1.0


def _context_value(value: float, minimum: float, maximum: float) -> float:
    return round(clamp(value, minimum, maximum), 6)


__all__ = (
    "appearance_fit",
    "distance",
    "generate_appearance",
    "signature",
    "visible_key",
)
