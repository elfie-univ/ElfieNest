"""从稳定随机种子生成精灵的个体外貌基因。"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .models import (
    PROFILE_SCHEMA_VERSION,
    AppearanceGenome,
    AppearanceMacro,
    AppearanceProportions,
    AppendageAppearance,
    BodyAppearance,
    CoatAppearance,
    ElfieIdentity,
    ElfieProfile,
    EmbodimentProfile,
    FaceAppearance,
    FurAppearance,
    ProfileProvenance,
)
from .species import get_species_profile

GENERATOR_VERSION = "appearance-v1"
VALID_HEIGHT_DIRECTIONS = ("short", "standard", "tall")
VALID_BUILD_DIRECTIONS = ("slim", "standard", "plump")


@dataclass(frozen=True)
class AppearanceGenerator:
    """只依赖显式种子的可重复外貌生成器。"""

    seed: int

    def generate(
        self,
        *,
        species_id: str,
        height_direction: str = "standard",
        build_direction: str = "standard",
    ) -> AppearanceGenome:
        species = get_species_profile(species_id)
        _validate_direction(
            "height_direction", height_direction, VALID_HEIGHT_DIRECTIONS
        )
        _validate_direction("build_direction", build_direction, VALID_BUILD_DIRECTIONS)
        rng = random.Random(self.seed)

        stature_z = _directed_z(rng, height_direction)
        body_fat_z = _directed_z(rng, build_direction)
        # 骨架粗壮和肌肉与胖瘦相关，但仍保留独立变化。
        frame_size_z = _bounded(0.28 * body_fat_z + rng.gauss(0.0, 0.58), -2.0, 2.0)
        muscularity_z = _bounded(0.12 * frame_size_z + rng.gauss(0.0, 0.62), -2.0, 2.0)

        def local(sigma: float = 0.34) -> float:
            return _truncated_normal(rng, 0.0, sigma, -1.0, 1.0)

        def unit(mean: float = 0.5, sigma: float = 0.20) -> float:
            return _truncated_normal(rng, mean, sigma, 0.0, 1.0)

        genome = AppearanceGenome(
            genome_version=1,
            species_profile_version=species.profile_version,
            seed=self.seed,
            macro=AppearanceMacro(
                stature_z=stature_z,
                frame_size_z=frame_size_z,
                body_fat_z=body_fat_z,
                muscularity_z=muscularity_z,
            ),
            proportions=AppearanceProportions(
                head_torso_bias=local(),
                neck_torso_bias=local(),
                arm_torso_bias=local(),
                leg_torso_bias=local(),
                shoulder_torso_bias=local(),
                hand_arm_bias=local(),
                paw_leg_bias=local(),
            ),
            body_bias=BodyAppearance(
                chest_fullness_bias=local(),
                waist_width_bias=local(),
                belly_depth_bias=local(),
                hip_width_bias=local(),
                hip_depth_bias=local(),
                arm_thickness_bias=local(),
                leg_thickness_bias=local(),
                neck_thickness_bias=local(),
                paw_fullness_bias=local(),
            ),
            face=FaceAppearance(
                skull_width_bias=local(),
                forehead_height_bias=local(),
                forehead_width_bias=local(),
                jaw_width_bias=local(),
                cheekbone_width_bias=local(),
                cheek_fullness_bias=local(),
                lower_face_fullness_bias=local(),
                muzzle_length_bias=local(),
                muzzle_width_bias=local(),
                muzzle_height_bias=local(),
                eye_size_bias=local(0.28),
                eye_spacing_bias=local(0.24),
                eye_height_bias=local(0.24),
                eye_tilt_bias=local(0.28),
                iris_size_bias=local(0.28),
                pupil_size_bias=local(0.28),
                eyelid_fold=unit(),
                upper_lid_openness_bias=local(0.26),
                nose_width_bias=local(),
                nose_height_bias=local(),
                nose_projection_bias=local(),
                mouth_width_bias=local(),
                mouth_height_bias=local(0.24),
                mouth_curve_bias=local(0.24),
                brow_height_bias=local(0.28),
                brow_angle_bias=local(0.28),
            ),
            appendages=AppendageAppearance(
                ear_size_bias=local(),
                ear_width_bias=local(),
                ear_tilt_bias=local(0.28),
                ear_droop=unit(0.18 if species_id == "fox" else 0.35, 0.17),
                ear_asymmetry=local(0.12),
                tail_length_bias=local(),
                tail_thickness_bias=local(),
            ),
            fur=FurAppearance(
                body_fur_length_bias=local(),
                head_tuft_bias=local(),
                cheek_ruff_bias=local(),
                chest_ruff_bias=local(),
                ear_tuft_bias=local(),
                limb_feathering_bias=local(),
                tail_fluff_bias=local(),
            ),
            coat=CoatAppearance(
                palette_id=rng.choice(species.palettes),
                pattern_id=rng.choice(species.patterns),
                primary_hue_shift=local(0.16),
                primary_saturation_bias=local(0.20),
                primary_value_bias=local(0.20),
                secondary_value_bias=local(0.20),
                eye_color_id=rng.choice(species.eye_colors),
                nose_color_id=rng.choice(species.nose_colors),
                pattern_coverage_bias=local(),
                pattern_scale_bias=local(),
                pattern_contrast_bias=local(),
                pattern_symmetry=unit(0.78, 0.14),
                face_mask_coverage_bias=local(),
                chest_patch_coverage_bias=local(),
                paw_patch_coverage_bias=local(),
                tail_tip_coverage_bias=local(),
            ),
            species_traits=(
                {
                    "black_leg_coverage": local(),
                    "tail_tip_coverage": local(),
                    "cheek_ruff_bias": local(),
                }
                if species_id == "fox"
                else {
                    "jowl_fullness_bias": local(),
                    "ear_fold_bias": local(),
                    "tail_curl_bias": local(),
                }
            ),
        )
        return genome


def create_visual_profile(
    *,
    elfie_id: str,
    display_name: str,
    species_id: str,
    seed: int,
    height_direction: str = "standard",
    build_direction: str = "standard",
) -> ElfieProfile:
    """创建当前阶段可直接持久化的视觉个体档案。"""
    appearance = AppearanceGenerator(seed).generate(
        species_id=species_id,
        height_direction=height_direction,
        build_direction=build_direction,
    )
    profile = ElfieProfile(
        schema_version=PROFILE_SCHEMA_VERSION,
        identity=ElfieIdentity(
            elfie_id=elfie_id,
            display_name=display_name,
            species_id=species_id,
        ),
        appearance=appearance,
        embodiment=EmbodimentProfile(
            primary_morphology="biped",
            supported_morphologies=("biped",),
            skeleton_profile_id="humanoid_mixamo_v1",
            capability_profile_id=f"{species_id}_biped_v1",
        ),
        provenance=ProfileProvenance(
            generator_version=GENERATOR_VERSION,
            master_seed=seed,
            appearance_seed=seed,
            user_choices={
                "height_direction": height_direction,
                "build_direction": build_direction,
                "primary_morphology": "biped",
            },
        ),
    )
    profile.validate()
    return profile


def _validate_direction(name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(f"{name} 必须是 {allowed}，收到 {value!r}")


def _directed_z(rng: random.Random, direction: str) -> float:
    means = {"short": -1.0, "standard": 0.0, "tall": 1.0}
    if direction in ("slim", "plump"):
        means = {"slim": -1.0, "standard": 0.0, "plump": 1.0}
    return _truncated_normal(rng, means[direction], 0.38, -2.0, 2.0)


def _truncated_normal(
    rng: random.Random,
    mean: float,
    sigma: float,
    minimum: float,
    maximum: float,
) -> float:
    for _ in range(32):
        value = rng.gauss(mean, sigma)
        if minimum <= value <= maximum:
            return round(value, 6)
    return round(_bounded(value, minimum, maximum), 6)


def _bounded(value: float, minimum: float, maximum: float) -> float:
    return round(max(minimum, min(maximum, value)), 6)
