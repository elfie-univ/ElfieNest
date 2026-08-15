"""从稳定随机种子生成精灵的个体外貌基因。"""

from __future__ import annotations

import random
from dataclasses import dataclass, fields, replace
from typing import Any, Mapping

from .models import (
    PROFILE_SCHEMA_VERSION,
    AppearanceGenome,
    AppearanceMacro,
    AppearanceProportions,
    AppendageAppearance,
    BodyAppearance,
    CoatAppearance,
    ElfieIdentity,
    ElfieOrigin,
    ElfieProfile,
    EmbodimentProfile,
    FaceAppearance,
    FurAppearance,
    ProfileProvenance,
)
from .species import get_species_profile
from .species_registry import SpeciesCatalog, current_species_catalog

GENERATOR_VERSION = "appearance-v1"
VALID_HEIGHT_DIRECTIONS = ("short", "standard", "tall")
VALID_BUILD_DIRECTIONS = ("slim", "standard", "plump")


@dataclass(frozen=True)
class AppearanceGenerator:
    """只依赖显式种子的可重复外貌生成器。"""

    seed: int
    catalog: SpeciesCatalog | None = None

    def generate(
        self,
        *,
        species_id: str,
        height_direction: str = "standard",
        build_direction: str = "standard",
        overrides: Mapping[str, Any] | None = None,
    ) -> AppearanceGenome:
        species = (
            self.catalog.definition(species_id, adoptable_only=True).appearance
            if self.catalog is not None
            else get_species_profile(species_id)
        )
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

        ear_distribution = species.distributions["ear_droop"]
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
                ear_droop=_truncated_normal(
                    rng,
                    ear_distribution.mean,
                    ear_distribution.standard_deviation,
                    ear_distribution.minimum,
                    ear_distribution.maximum,
                ),
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
            species_traits={name: local() for name in species.species_traits},
        )
        genome = _apply_appearance_overrides(genome, overrides)
        _validate_generated_appearance(genome, species_id)
        return genome


def create_visual_profile(
    *,
    elfie_id: str,
    display_name: str,
    species_id: str,
    seed: int,
    height_direction: str = "standard",
    build_direction: str = "standard",
    appearance_overrides: Mapping[str, Any] | None = None,
    origin: ElfieOrigin | None = None,
    catalog: SpeciesCatalog | None = None,
) -> ElfieProfile:
    """创建当前阶段可直接持久化的视觉个体档案。"""
    catalog = catalog or current_species_catalog()
    species_definition = catalog.definition(species_id, adoptable_only=True)
    appearance = AppearanceGenerator(seed, catalog=catalog).generate(
        species_id=species_id,
        height_direction=height_direction,
        build_direction=build_direction,
        overrides=appearance_overrides,
    )
    profile = ElfieProfile(
        schema_version=PROFILE_SCHEMA_VERSION,
        identity=ElfieIdentity(
            elfie_id=elfie_id,
            display_name=display_name,
            species_id=species_id,
            origin=origin or ElfieOrigin(),
        ),
        appearance=appearance,
        embodiment=EmbodimentProfile(
            primary_morphology="biped",
            supported_morphologies=("biped",),
            skeleton_profile_id="humanoid_mixamo_v1",
            capability_profile_id=species_definition.godot_package_id,
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
    profile.validate(catalog=catalog)
    return profile


def _apply_appearance_overrides(
    genome: AppearanceGenome,
    overrides: Mapping[str, Any] | None,
) -> AppearanceGenome:
    """把显式初始化参数覆盖到种子生成的外貌上，并拒绝未知字段。"""
    if overrides is None:
        return genome
    if not isinstance(overrides, Mapping):
        raise ValueError("appearance_overrides 必须是映射")

    group_types = {
        "macro": AppearanceMacro,
        "proportions": AppearanceProportions,
        "body_bias": BodyAppearance,
        "face": FaceAppearance,
        "appendages": AppendageAppearance,
        "fur": FurAppearance,
        "coat": CoatAppearance,
    }
    allowed_groups = set(group_types) | {"species_traits"}
    unknown_groups = sorted(set(overrides) - allowed_groups)
    if unknown_groups:
        raise ValueError(
            "appearance_overrides 包含未知分组: " + ", ".join(unknown_groups)
        )

    updates: dict[str, Any] = {}
    for group_name, model_type in group_types.items():
        if group_name not in overrides:
            continue
        raw_group = overrides[group_name]
        if not isinstance(raw_group, Mapping):
            raise ValueError(f"appearance_overrides.{group_name} 必须是映射")
        allowed_fields = {item.name for item in fields(model_type)}
        unknown_fields = sorted(set(raw_group) - allowed_fields)
        if unknown_fields:
            raise ValueError(
                f"appearance_overrides.{group_name} 包含未知字段: "
                + ", ".join(unknown_fields)
            )
        updates[group_name] = replace(
            getattr(genome, group_name),
            **dict(raw_group),
        )

    if "species_traits" in overrides:
        raw_traits = overrides["species_traits"]
        if not isinstance(raw_traits, Mapping):
            raise ValueError("appearance_overrides.species_traits 必须是映射")
        unknown_traits = sorted(set(raw_traits) - set(genome.species_traits))
        if unknown_traits:
            raise ValueError(
                "appearance_overrides.species_traits 包含当前物种不支持的字段: "
                + ", ".join(unknown_traits)
            )
        updates["species_traits"] = {
            **genome.species_traits,
            **dict(raw_traits),
        }

    return replace(genome, **updates)


def _validate_generated_appearance(
    genome: AppearanceGenome,
    species_id: str,
) -> None:
    validation_profile = ElfieProfile(
        schema_version=PROFILE_SCHEMA_VERSION,
        identity=ElfieIdentity(
            elfie_id="appearance-validation",
            display_name="appearance-validation",
            species_id=species_id,
        ),
        appearance=genome,
        provenance=ProfileProvenance(
            generator_version=GENERATOR_VERSION,
            master_seed=genome.seed,
            appearance_seed=genome.seed,
        ),
    )
    validation_profile.validate()


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
