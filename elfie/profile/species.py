"""Typed species appearance configuration consumed by the Profile domain.

The domain owns the shape of the configuration, not its YAML source. A
composition root injects a :class:`SpeciesCatalog` built by Infrastructure.
Keeping the value objects here lets Profile and Genesis stay independent from
filesystem paths and configuration parsers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


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
    supported_controls: tuple[str, ...] = ()
    control_options: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    control_ranges: Mapping[str, ScaleRange] = field(default_factory=dict)
    proportion_scales: Mapping[str, ScaleRange] = field(default_factory=dict)
    shape_correlations: Mapping[str, CorrelationWeights] = field(default_factory=dict)
    distributions: Mapping[str, Distribution] = field(default_factory=dict)
    species_traits: tuple[str, ...] = ()


def get_species_profile(species_id: str) -> SpeciesAppearanceProfile:
    """Resolve one profile from the configured catalog.

    This indirection is deliberately kept for existing domain call sites. It
    does not discover files or contain species data; the catalog must have
    been injected by the composition root first.
    """

    from .species_registry import get_species_definition  # noqa: PLC0415

    return get_species_definition(species_id).appearance


__all__ = (
    "CorrelationWeights",
    "Distribution",
    "ScaleRange",
    "SpeciesAppearanceProfile",
    "get_species_profile",
)
