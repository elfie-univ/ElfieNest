"""当前可领养物种及其外貌解析范围。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from .models import SUPPORTED_SPECIES


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
class SpeciesAppearanceProfile:
    species_id: str
    profile_version: int
    scene_id: str
    stature_scale: ScaleRange
    build_scale: ScaleRange
    build_weights: CorrelationWeights
    proportion_scales: Dict[str, ScaleRange]
    shape_correlations: Dict[str, CorrelationWeights]
    palettes: tuple[str, ...]
    patterns: tuple[str, ...]
    eye_colors: tuple[str, ...]
    nose_colors: tuple[str, ...]


_SPECIES_PROFILES = {
    "fox": SpeciesAppearanceProfile(
        species_id="fox",
        profile_version=1,
        scene_id="fox",
        stature_scale=ScaleRange(0.90, 1.0, 1.10),
        build_scale=ScaleRange(0.90, 1.0, 1.10),
        build_weights=CorrelationWeights(0.55, 0.30, 0.15),
        proportion_scales={
            "HeadScale": ScaleRange(0.91, 1.0, 1.09),
            "NeckLength": ScaleRange(0.86, 1.0, 1.14),
            "ArmLength": ScaleRange(0.91, 1.0, 1.09),
            "LegLength": ScaleRange(0.90, 1.0, 1.10),
            "ShoulderWidth": ScaleRange(0.91, 1.0, 1.09),
            "HandScale": ScaleRange(0.91, 1.0, 1.09),
            "PawScale": ScaleRange(0.90, 1.0, 1.10),
            "TailLength": ScaleRange(0.86, 1.0, 1.14),
            "EyeScale": ScaleRange(0.91, 1.0, 1.09),
            "EyeSpacing": ScaleRange(0.95, 1.0, 1.05),
            "EyeHeight": ScaleRange(0.96, 1.0, 1.04),
        },
        shape_correlations={
            "Body_ChestFullness": CorrelationWeights(0.48, 0.22, 0.18, 0.30),
            "Body_WaistWidth": CorrelationWeights(0.68, 0.16, 0.0, 0.25),
            "Body_BellyDepth": CorrelationWeights(0.88, 0.0, 0.0, 0.25),
            "Body_HipWidth": CorrelationWeights(0.62, 0.24, 0.0, 0.25),
            "Body_HipDepth": CorrelationWeights(0.70, 0.0, 0.0, 0.25),
            "Body_ArmThickness": CorrelationWeights(0.72, 0.18, 0.16, 0.25),
            "Body_LegThickness": CorrelationWeights(0.76, 0.18, 0.16, 0.20),
            "Body_NeckThickness": CorrelationWeights(0.66, 0.18, 0.0, 0.20),
            "Body_PawFullness": CorrelationWeights(0.44, 0.20, 0.0, 0.30),
            "Face_CheekFullness": CorrelationWeights(0.62, 0.14, 0.0, 0.30),
            "Face_LowerFullness": CorrelationWeights(0.60, 0.0, 0.0, 0.28),
        },
        palettes=("red", "golden", "cross", "silver", "melanistic", "pale"),
        patterns=("classic", "bicolor", "cross", "face_mask"),
        eye_colors=("amber", "brown", "green", "blue_gray"),
        nose_colors=("black", "dark_brown", "charcoal"),
    ),
    "dog": SpeciesAppearanceProfile(
        species_id="dog",
        profile_version=1,
        scene_id="dog",
        stature_scale=ScaleRange(0.90, 1.0, 1.10),
        build_scale=ScaleRange(0.90, 1.0, 1.10),
        build_weights=CorrelationWeights(0.55, 0.30, 0.15),
        proportion_scales={
            "HeadScale": ScaleRange(0.90, 1.0, 1.10),
            "NeckLength": ScaleRange(0.86, 1.0, 1.14),
            "ArmLength": ScaleRange(0.90, 1.0, 1.10),
            "LegLength": ScaleRange(0.90, 1.0, 1.10),
            "ShoulderWidth": ScaleRange(0.89, 1.0, 1.11),
            "HandScale": ScaleRange(0.90, 1.0, 1.10),
            "PawScale": ScaleRange(0.89, 1.0, 1.11),
            "TailLength": ScaleRange(0.90, 1.0, 1.10),
            "EyeScale": ScaleRange(0.90, 1.0, 1.10),
            "EyeSpacing": ScaleRange(0.94, 1.0, 1.06),
            "EyeHeight": ScaleRange(0.95, 1.0, 1.05),
        },
        shape_correlations={
            "Body_ChestFullness": CorrelationWeights(0.52, 0.26, 0.20, 0.30),
            "Body_WaistWidth": CorrelationWeights(0.74, 0.18, 0.0, 0.25),
            "Body_BellyDepth": CorrelationWeights(0.92, 0.0, 0.0, 0.25),
            "Body_HipWidth": CorrelationWeights(0.67, 0.26, 0.0, 0.25),
            "Body_HipDepth": CorrelationWeights(0.74, 0.0, 0.0, 0.25),
            "Body_ArmThickness": CorrelationWeights(0.77, 0.22, 0.20, 0.25),
            "Body_LegThickness": CorrelationWeights(0.82, 0.22, 0.20, 0.20),
            "Body_NeckThickness": CorrelationWeights(0.72, 0.22, 0.0, 0.20),
            "Body_PawFullness": CorrelationWeights(0.50, 0.22, 0.0, 0.30),
            "Face_CheekFullness": CorrelationWeights(0.68, 0.16, 0.0, 0.30),
            "Face_LowerFullness": CorrelationWeights(0.64, 0.0, 0.0, 0.28),
        },
        palettes=(
            "black",
            "white",
            "cream",
            "golden",
            "red_brown",
            "chocolate",
            "gray",
        ),
        patterns=("solid", "bicolor", "tricolor", "face_mask"),
        eye_colors=("brown", "amber", "blue", "hazel"),
        nose_colors=("black", "dark_brown", "charcoal"),
    ),
    "cat": SpeciesAppearanceProfile(
        species_id="cat",
        profile_version=1,
        scene_id="cat",
        stature_scale=ScaleRange(0.88, 0.98, 1.08),
        build_scale=ScaleRange(0.86, 0.96, 1.08),
        build_weights=CorrelationWeights(0.36, 0.24, 0.18),
        proportion_scales={
            "HeadScale": ScaleRange(0.92, 1.0, 1.10),
            "NeckLength": ScaleRange(0.88, 1.0, 1.12),
            "ArmLength": ScaleRange(0.92, 1.0, 1.08),
            "LegLength": ScaleRange(0.92, 1.0, 1.12),
            "ShoulderWidth": ScaleRange(0.88, 0.98, 1.08),
            "HandScale": ScaleRange(0.88, 0.98, 1.08),
            "PawScale": ScaleRange(0.86, 0.96, 1.06),
            "TailLength": ScaleRange(0.90, 1.0, 1.14),
            "EyeScale": ScaleRange(0.94, 1.04, 1.14),
            "EyeSpacing": ScaleRange(0.94, 1.0, 1.06),
            "EyeHeight": ScaleRange(0.96, 1.0, 1.04),
        },
        shape_correlations={
            "Body_ChestFullness": CorrelationWeights(0.38, 0.24, 0.18, 0.28),
            "Body_WaistWidth": CorrelationWeights(0.52, 0.16, 0.0, 0.24),
            "Body_BellyDepth": CorrelationWeights(0.68, 0.0, 0.0, 0.24),
            "Body_HipWidth": CorrelationWeights(0.48, 0.22, 0.0, 0.24),
            "Body_HipDepth": CorrelationWeights(0.56, 0.0, 0.0, 0.24),
            "Body_ArmThickness": CorrelationWeights(0.52, 0.18, 0.22, 0.24),
            "Body_LegThickness": CorrelationWeights(0.58, 0.18, 0.22, 0.20),
            "Body_NeckThickness": CorrelationWeights(0.48, 0.18, 0.0, 0.20),
            "Body_PawFullness": CorrelationWeights(0.34, 0.18, 0.0, 0.28),
            "Face_CheekFullness": CorrelationWeights(0.50, 0.12, 0.0, 0.28),
            "Face_LowerFullness": CorrelationWeights(0.42, 0.0, 0.0, 0.26),
        },
        palettes=("black", "white", "cream", "ginger", "gray", "calico", "tuxedo"),
        patterns=("solid", "tabby", "bicolor", "calico", "tuxedo"),
        eye_colors=("green", "amber", "blue", "hazel", "blue_gray"),
        nose_colors=("pink", "black", "dark_brown", "charcoal"),
    ),
}


def get_species_profile(species_id: str) -> SpeciesAppearanceProfile:
    try:
        return _SPECIES_PROFILES[species_id]
    except KeyError as exc:
        raise ValueError(
            f"不支持的 species_id={species_id!r}，可选: {', '.join(SUPPORTED_SPECIES)}"
        ) from exc
