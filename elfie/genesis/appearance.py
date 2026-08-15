"""Appearance proposal and distance helpers for Genesis."""

from __future__ import annotations

import hashlib
import random

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
    return AppearanceGenerator(seed, catalog=catalog).generate(
        species_id=species_id,
        height_direction=height,
        build_direction=build,
        overrides=_overrides(species_id, intent, role, rng, catalog=catalog),
    )


def signature(genome: AppearanceGenome) -> tuple[float, ...]:
    categories = (
        genome.coat.palette_id,
        genome.coat.pattern_id,
        genome.coat.eye_color_id,
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
        *category_values,
    )


def appearance_fit(genome: AppearanceGenome, intent: GenesisAppearanceIntent) -> float:
    values = {
        "stature": genome.macro.stature_z / 2.0,
        "build": genome.macro.body_fat_z / 2.0,
        "face": genome.face.cheek_fullness_bias,
        "signature": genome.coat.pattern_contrast_bias,
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
    if intent.signature == "warm":
        species = (
            catalog.definition(species_id, adoptable_only=True)
            if catalog is not None
            else get_species_definition(species_id, adoptable_only=True)
        )
        preferences = (
            species.genesis.appearance_preferences if species.genesis is not None else {}
        )
        preferred = tuple(
            option
            for option in preferences.get("warm", ())
            if option in species.appearance.palettes
        )
        palettes = preferred or species.appearance.palettes
        overrides["coat"] = {"palette_id": rng.choice(palettes)}
    elif intent.signature == "marked":
        species = (
            catalog.definition(species_id, adoptable_only=True)
            if catalog is not None
            else get_species_definition(species_id, adoptable_only=True)
        )
        preferences = (
            species.genesis.appearance_preferences if species.genesis is not None else {}
        )
        preferred = tuple(
            option
            for option in preferences.get("marked", ())
            if option in species.appearance.patterns
        )
        patterns = preferred or species.appearance.patterns
        overrides["coat"] = {
            "pattern_id": rng.choice(patterns),
            "pattern_contrast_bias": 0.45,
        }
    elif intent.signature == "ears":
        overrides["appendages"] = {
            "ear_size_bias": rng.uniform(0.35, 0.80),
            "ear_tilt_bias": rng.uniform(-0.55, 0.55),
        }
    return overrides


__all__ = ("appearance_fit", "distance", "generate_appearance", "signature")
