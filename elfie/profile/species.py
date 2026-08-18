"""Typed species appearance configuration consumed by the Profile domain.

The domain owns the shape of the configuration, not its YAML source. A
composition root injects a :class:`SpeciesCatalog` built by Infrastructure.
Keeping the value objects here lets Profile and Genesis stay independent from
filesystem paths and configuration parsers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

APPEARANCE_REGION_IDS = (
    "head_tuft",
    "forehead_mark_zone",
    "ear_pair",
    "ear_tip_pair",
    "cheek_fluff",
    "chest_tuft",
    "belly_center",
    "forearm_paw_pair",
    "elbow_cuff_pair",
    "lower_leg_foot_pair",
    "knee_cuff_pair",
    "tail_tip",
    "tail_underside",
)


@dataclass(frozen=True)
class ScaleRange:
    minimum: float
    base: float
    maximum: float


@dataclass(frozen=True)
class CorrelationWeights:
    body_fat: float = 0.0
    frame_size: float = 0.0
    muscularity: float = 0.0
    local_bias: float = 0.0


@dataclass(frozen=True)
class Distribution:
    """A bounded normal distribution used by deterministic Genesis output."""

    mean: float = 0.0
    standard_deviation: float = 0.34
    minimum: float = -1.0
    maximum: float = 1.0


@dataclass(frozen=True)
class AppearanceRegionRule:
    """One semantic region and the operations it permits."""

    mode: str
    allowed_colors: tuple[str, ...] = ()
    allowed_grades: tuple[str, ...] = ()
    source_mid_luma: float = 0.5
    default_intensity: float = 0.8


@dataclass(frozen=True)
class RegionAccentSpec:
    """One accent in a product-reviewed region recipe."""

    region_id: str
    color_id: str
    grade_id: str = "L1"
    intensity: float = 0.8


@dataclass(frozen=True)
class AppearanceRegionRecipe:
    recipe_id: str
    accents: tuple[RegionAccentSpec, ...] = ()


@dataclass(frozen=True)
class AppearanceMarkingRule:
    """Allowed placements and colors for one local symbol."""

    placements: tuple[str, ...]
    allowed_colors: tuple[str, ...]


@dataclass(frozen=True)
class SpeciesAppearanceProfile:
    """Semantic appearance controls and per-species generation ranges."""

    species_id: str
    profile_version: int
    stature_scale: ScaleRange
    build_scale: ScaleRange
    build_weights: CorrelationWeights
    palettes: tuple[str, ...]
    patterns: tuple[str, ...]
    eye_colors: tuple[str, ...]
    nose_colors: tuple[str, ...]
    pattern_color_slots: Mapping[str, int] = field(default_factory=dict)
    pattern_layouts: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    markings: tuple[str, ...] = ("none",)
    marking_placements: tuple[str, ...] = ("none",)
    supported_controls: tuple[str, ...] = ()
    control_options: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    control_ranges: Mapping[str, ScaleRange] = field(default_factory=dict)
    proportion_scales: Mapping[str, ScaleRange] = field(default_factory=dict)
    shape_correlations: Mapping[str, CorrelationWeights] = field(default_factory=dict)
    distributions: Mapping[str, Distribution] = field(default_factory=dict)
    species_traits: tuple[str, ...] = ()
    region_rules: Mapping[str, AppearanceRegionRule] = field(default_factory=dict)
    region_recipes: Mapping[str, AppearanceRegionRecipe] = field(default_factory=dict)
    region_recipe_order: tuple[str, ...] = ()
    marking_rules: Mapping[str, AppearanceMarkingRule] = field(default_factory=dict)
    batch_palette_order: tuple[str, ...] = ()
    batch_recipe_order: tuple[str, ...] = ()
    batch_marking_order: tuple[str, ...] = ()
    max_region_accents: int = 2
    max_marks: int = 1
    max_forehead_marks: int = 1


def get_species_profile(species_id: str) -> SpeciesAppearanceProfile:
    """Resolve one profile from the configured catalog.

    This indirection is deliberately kept for existing domain call sites. It
    does not discover files or contain species data; the catalog must have
    been injected by the composition root first.
    """

    from .species_registry import get_species_definition  # noqa: PLC0415

    return get_species_definition(species_id).appearance


__all__ = (
    "APPEARANCE_REGION_IDS",
    "AppearanceMarkingRule",
    "AppearanceRegionRecipe",
    "AppearanceRegionRule",
    "CorrelationWeights",
    "Distribution",
    "RegionAccentSpec",
    "ScaleRange",
    "SpeciesAppearanceProfile",
    "get_species_profile",
)
