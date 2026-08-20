"""把稳定外貌基因解析为 Godot 可直接应用的参数。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict

from .models import AppearanceGenome, ElfieProfile
from .species import (
    CorrelationWeights,
    ScaleRange,
    SpeciesAppearanceProfile,
    get_species_profile,
)
from .species_registry import SpeciesCatalog


@dataclass(frozen=True)
class ResolvedAppearance:
    species_id: str
    profile_version: int
    height_scale: float
    build_scale: float
    height_label: str
    build_label: str
    bone_scales: Dict[str, float]
    blend_shapes: Dict[str, float]
    material_parameters: Dict[str, Any]
    species_traits: Dict[str, float]

    def to_payload(self) -> Dict[str, Any]:
        return asdict(self)


class AppearanceResolver:
    """集中执行相关性、范围和资源命名映射。"""

    def __init__(self, catalog: SpeciesCatalog | None = None) -> None:
        self._catalog = catalog

    def resolve(self, profile: ElfieProfile) -> ResolvedAppearance:
        profile.validate(catalog=self._catalog)
        species = (
            self._catalog.definition(profile.identity.species_id).appearance
            if self._catalog is not None
            else get_species_profile(profile.identity.species_id)
        )
        genome = profile.appearance
        if genome.species_profile_version != species.profile_version:
            raise ValueError(
                "外貌基因使用的物种配置版本与当前解析器不一致: "
                f"{genome.species_profile_version} != {species.profile_version}"
            )

        height_scale = _map_z(genome.macro.stature_z, species.stature_scale)
        build_z = _clamp(
            _correlated(
                species.build_weights,
                genome.macro.body_fat_z,
                genome.macro.frame_size_z,
                genome.macro.muscularity_z,
                0.0,
            ),
            -2.0,
            2.0,
        )
        build_scale = _map_z(build_z, species.build_scale)

        return ResolvedAppearance(
            species_id=profile.identity.species_id,
            profile_version=species.profile_version,
            height_scale=height_scale,
            build_scale=build_scale,
            height_label=_label(genome.macro.stature_z, "short", "tall"),
            build_label=_label(build_z, "slim", "plump"),
            bone_scales=self._resolve_bones(genome, species),
            blend_shapes=self._resolve_blend_shapes(genome, species),
            material_parameters=self._resolve_materials(genome, species),
            species_traits=dict(genome.species_traits),
        )

    @staticmethod
    def _resolve_bones(
        genome: AppearanceGenome, species: SpeciesAppearanceProfile
    ) -> Dict[str, float]:
        p = genome.proportions
        biases = {
            "HeadScale": p.head_torso_bias,
            "NeckLength": p.neck_torso_bias,
            "ArmLength": p.arm_torso_bias,
            "LegLength": p.leg_torso_bias,
            "ShoulderWidth": p.shoulder_torso_bias,
            "HandScale": p.hand_arm_bias,
            "PawScale": p.paw_leg_bias,
            "TailLength": genome.appendages.tail_length_bias,
            "EyeScale": genome.face.eye_size_bias,
            "EyeSpacing": genome.face.eye_spacing_bias,
            "EyeHeight": genome.face.eye_height_bias,
        }
        return {
            name: _map_bias(value, species.proportion_scales[name])
            for name, value in biases.items()
        }

    @staticmethod
    def _resolve_blend_shapes(
        genome: AppearanceGenome, species: SpeciesAppearanceProfile
    ) -> Dict[str, float]:
        body = genome.body_bias
        face = genome.face

        values = {
            "Body_ChestFullness": _shape_value(
                species, "Body_ChestFullness", genome, body.chest_fullness_bias
            ),
            "Body_WaistWidth": _shape_value(
                species, "Body_WaistWidth", genome, body.waist_width_bias
            ),
            "Body_BellyDepth": _shape_value(
                species, "Body_BellyDepth", genome, body.belly_depth_bias
            ),
            "Body_HipWidth": _shape_value(
                species, "Body_HipWidth", genome, body.hip_width_bias
            ),
            "Body_HipDepth": _shape_value(
                species, "Body_HipDepth", genome, body.hip_depth_bias
            ),
            "Body_ArmThickness": _shape_value(
                species, "Body_ArmThickness", genome, body.arm_thickness_bias
            ),
            "Body_LegThickness": _shape_value(
                species, "Body_LegThickness", genome, body.leg_thickness_bias
            ),
            "Body_NeckThickness": _shape_value(
                species, "Body_NeckThickness", genome, body.neck_thickness_bias
            ),
            "Body_PawFullness": _shape_value(
                species, "Body_PawFullness", genome, body.paw_fullness_bias
            ),
            "Face_SkullWidth": face.skull_width_bias,
            "Face_ForeheadHeight": face.forehead_height_bias,
            "Face_ForeheadWidth": face.forehead_width_bias,
            "Face_JawWidth": face.jaw_width_bias,
            "Face_CheekboneWidth": face.cheekbone_width_bias,
            "Face_CheekFullness": _shape_value(
                species, "Face_CheekFullness", genome, face.cheek_fullness_bias
            ),
            "Face_LowerFullness": _shape_value(
                species, "Face_LowerFullness", genome, face.lower_face_fullness_bias
            ),
            "Face_MuzzleLength": face.muzzle_length_bias,
            "Face_MuzzleWidth": face.muzzle_width_bias,
            "Face_MuzzleHeight": face.muzzle_height_bias,
            "Face_EyeSocketSize": face.eye_size_bias,
            "Face_EyeTilt": face.eye_tilt_bias,
            "Face_UpperLidOpen": face.upper_lid_openness_bias,
            "Face_NoseWidth": face.nose_width_bias,
            "Face_NoseHeight": face.nose_height_bias,
            "Face_NoseProjection": face.nose_projection_bias,
            "Face_MouthWidth": face.mouth_width_bias,
            "Face_MouthHeight": face.mouth_height_bias,
            "Face_MouthCurve": face.mouth_curve_bias,
            "Face_BrowHeight": face.brow_height_bias,
            "Face_BrowAngle": face.brow_angle_bias,
            "Ear_Size": genome.appendages.ear_size_bias,
            "Ear_Width": genome.appendages.ear_width_bias,
            "Ear_Tilt": genome.appendages.ear_tilt_bias,
            "Tail_Thickness": genome.appendages.tail_thickness_bias,
        }
        resolved: Dict[str, float] = {}
        for name, value in values.items():
            _add_signed(resolved, name, _clamp(value, -1.0, 1.0))

        resolved["Face_EyelidFold"] = round(face.eyelid_fold, 6)
        resolved["Ear_Droop"] = round(genome.appendages.ear_droop, 6)
        resolved.update(_resolve_fur(genome))
        resolved.update(_resolve_correctives(resolved))
        return resolved

    @staticmethod
    def _resolve_materials(
        genome: AppearanceGenome,
        species: SpeciesAppearanceProfile,
    ) -> Dict[str, Any]:
        coat = genome.coat
        primary_color = coat.primary_color_id or coat.palette_id
        secondary_color = coat.secondary_color_id or primary_color
        accent_color = coat.accent_color_id or secondary_color
        face_mask_color = coat.face_mask_color_id or secondary_color
        material: Dict[str, Any] = {
            "palette_id": coat.palette_id,
            "region_recipe_id": coat.region_recipe_id,
            "pattern_id": coat.pattern_id,
            "pattern_layout_id": coat.pattern_layout_id or coat.pattern_id,
            "primary_color_id": primary_color,
            "secondary_color_id": secondary_color,
            "accent_color_id": accent_color,
            "face_mask_color_id": face_mask_color,
            "marking_color_id": coat.marking_color_id or secondary_color,
            "marking_id": coat.marking_id,
            "marking_placement": coat.marking_placement,
            "marking_scale": coat.marking_scale,
            "marking_intensity": coat.marking_intensity,
            "primary_hue_shift": coat.primary_hue_shift,
            "primary_saturation_bias": coat.primary_saturation_bias,
            "primary_value_bias": coat.primary_value_bias,
            "secondary_value_bias": coat.secondary_value_bias,
            "eye_color_id": coat.eye_color_id,
            "nose_color_id": coat.nose_color_id,
            "pattern_coverage_bias": coat.pattern_coverage_bias,
            "pattern_scale_bias": coat.pattern_scale_bias,
            "pattern_contrast_bias": coat.pattern_contrast_bias,
            "pattern_symmetry": coat.pattern_symmetry,
            "face_mask_coverage_bias": coat.face_mask_coverage_bias,
            "chest_patch_coverage_bias": coat.chest_patch_coverage_bias,
            "paw_patch_coverage_bias": coat.paw_patch_coverage_bias,
            "tail_tip_coverage_bias": coat.tail_tip_coverage_bias,
            "iris_size_bias": genome.face.iris_size_bias,
            "pupil_size_bias": genome.face.pupil_size_bias,
        }
        for index in range(3):
            accent = (
                genome.coat.region_accents[index]
                if index < len(genome.coat.region_accents)
                else None
            )
            if accent is None:
                material.update(
                    {
                        f"region_{index}_id": "none",
                        f"region_{index}_color_id": primary_color,
                        f"region_{index}_grade_id": "L1",
                        f"region_{index}_intensity": 0.0,
                        f"region_{index}_source_mid_luma": 0.5,
                    }
                )
                continue
            rule = species.region_rules[accent.region_id]
            material.update(
                {
                    f"region_{index}_id": accent.region_id,
                    f"region_{index}_color_id": accent.color_id,
                    f"region_{index}_grade_id": accent.grade_id,
                    f"region_{index}_intensity": accent.intensity,
                    f"region_{index}_source_mid_luma": rule.source_mid_luma,
                }
            )
        return material


def _resolve_fur(genome: AppearanceGenome) -> Dict[str, float]:
    values = {
        "Fur_BodyLength": genome.fur.body_fur_length_bias,
        "Fur_HeadTuft": genome.fur.head_tuft_bias,
        "Fur_CheekRuff": genome.fur.cheek_ruff_bias,
        "Fur_ChestRuff": genome.fur.chest_ruff_bias,
        "Fur_EarTuft": genome.fur.ear_tuft_bias,
        "Fur_LimbFeathering": genome.fur.limb_feathering_bias,
        "Fur_TailFluff": genome.fur.tail_fluff_bias,
    }
    # 毛发母版以 0 为无额外轮廓，因此只发送正向权重。
    return {name: round(max(0.0, value), 6) for name, value in values.items()}


def _resolve_correctives(blend_shapes: Dict[str, float]) -> Dict[str, float]:
    large_eye = blend_shapes.get("Face_EyeSocketSize_Pos", 0.0)
    narrow_face = blend_shapes.get("Face_SkullWidth_Neg", 0.0)
    return {
        "Corrective_LargeEye_Eyelid": round(max(0.0, (large_eye - 0.55) / 0.45), 6),
        "Corrective_NarrowFace_EyeContainment": round(
            max(0.0, min(large_eye, narrow_face)), 6
        ),
    }


def _add_signed(target: Dict[str, float], name: str, value: float) -> None:
    target[f"{name}_Pos"] = round(max(value, 0.0), 6)
    target[f"{name}_Neg"] = round(max(-value, 0.0), 6)


def _normalized(value: float) -> float:
    # 宏观潜变量范围更宽，除以 2 后再进入 Shape Key 的 0..1 极值区间。
    return _clamp(value / 2.0, -1.0, 1.0)


def _map_z(value: float, scale_range: ScaleRange) -> float:
    normalized = _clamp(value / 2.0, -1.0, 1.0)
    if normalized < 0.0:
        result = (
            scale_range.base + (scale_range.base - scale_range.minimum) * normalized
        )
    else:
        result = (
            scale_range.base + (scale_range.maximum - scale_range.base) * normalized
        )
    return round(result, 6)


def _map_bias(value: float, scale_range: ScaleRange) -> float:
    value = _clamp(value, -1.0, 1.0)
    if value >= 0:
        result = scale_range.base + (scale_range.maximum - scale_range.base) * value
    else:
        result = scale_range.base + (scale_range.base - scale_range.minimum) * value
    return round(result, 6)


def _shape_value(
    species: SpeciesAppearanceProfile,
    name: str,
    genome: AppearanceGenome,
    local_bias: float,
) -> float:
    return _normalized(
        _correlated(
            species.shape_correlations[name],
            genome.macro.body_fat_z,
            genome.macro.frame_size_z,
            genome.macro.muscularity_z,
            local_bias,
        )
    )


def _correlated(
    weights: CorrelationWeights,
    body_fat: float,
    frame_size: float,
    muscularity: float,
    local_bias: float,
) -> float:
    return (
        weights.body_fat * body_fat
        + weights.frame_size * frame_size
        + weights.muscularity * muscularity
        + weights.local_bias * local_bias
    )


def _label(value: float, negative: str, positive: str) -> str:
    if value <= -0.45:
        return negative
    if value >= 0.45:
        return positive
    return "standard"


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
