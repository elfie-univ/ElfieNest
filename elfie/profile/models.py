"""精灵视觉身份的类型化数据模型。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, Type, TypeVar

PROFILE_SCHEMA_VERSION = 1
SUPPORTED_SPECIES = ("dog", "fox")
SUPPORTED_MORPHOLOGIES = ("biped", "quadruped")


@dataclass(frozen=True)
class AppearanceMacro:
    stature_z: float = 0.0
    frame_size_z: float = 0.0
    body_fat_z: float = 0.0
    muscularity_z: float = 0.0


@dataclass(frozen=True)
class AppearanceProportions:
    head_torso_bias: float = 0.0
    neck_torso_bias: float = 0.0
    arm_torso_bias: float = 0.0
    leg_torso_bias: float = 0.0
    shoulder_torso_bias: float = 0.0
    hand_arm_bias: float = 0.0
    paw_leg_bias: float = 0.0


@dataclass(frozen=True)
class BodyAppearance:
    chest_fullness_bias: float = 0.0
    waist_width_bias: float = 0.0
    belly_depth_bias: float = 0.0
    hip_width_bias: float = 0.0
    hip_depth_bias: float = 0.0
    arm_thickness_bias: float = 0.0
    leg_thickness_bias: float = 0.0
    neck_thickness_bias: float = 0.0
    paw_fullness_bias: float = 0.0


@dataclass(frozen=True)
class FaceAppearance:
    skull_width_bias: float = 0.0
    forehead_height_bias: float = 0.0
    forehead_width_bias: float = 0.0
    jaw_width_bias: float = 0.0
    cheekbone_width_bias: float = 0.0
    cheek_fullness_bias: float = 0.0
    lower_face_fullness_bias: float = 0.0
    muzzle_length_bias: float = 0.0
    muzzle_width_bias: float = 0.0
    muzzle_height_bias: float = 0.0
    eye_size_bias: float = 0.0
    eye_spacing_bias: float = 0.0
    eye_height_bias: float = 0.0
    eye_tilt_bias: float = 0.0
    iris_size_bias: float = 0.0
    pupil_size_bias: float = 0.0
    eyelid_fold: float = 0.5
    upper_lid_openness_bias: float = 0.0
    nose_width_bias: float = 0.0
    nose_height_bias: float = 0.0
    nose_projection_bias: float = 0.0
    mouth_width_bias: float = 0.0
    mouth_height_bias: float = 0.0
    mouth_curve_bias: float = 0.0
    brow_height_bias: float = 0.0
    brow_angle_bias: float = 0.0


@dataclass(frozen=True)
class AppendageAppearance:
    ear_size_bias: float = 0.0
    ear_width_bias: float = 0.0
    ear_tilt_bias: float = 0.0
    ear_droop: float = 0.0
    ear_asymmetry: float = 0.0
    tail_length_bias: float = 0.0
    tail_thickness_bias: float = 0.0


@dataclass(frozen=True)
class FurAppearance:
    body_fur_length_bias: float = 0.0
    head_tuft_bias: float = 0.0
    cheek_ruff_bias: float = 0.0
    chest_ruff_bias: float = 0.0
    ear_tuft_bias: float = 0.0
    limb_feathering_bias: float = 0.0
    tail_fluff_bias: float = 0.0


@dataclass(frozen=True)
class CoatAppearance:
    palette_id: str = "default"
    pattern_id: str = "solid"
    primary_hue_shift: float = 0.0
    primary_saturation_bias: float = 0.0
    primary_value_bias: float = 0.0
    secondary_value_bias: float = 0.0
    eye_color_id: str = "brown"
    nose_color_id: str = "black"
    pattern_coverage_bias: float = 0.0
    pattern_scale_bias: float = 0.0
    pattern_contrast_bias: float = 0.0
    pattern_symmetry: float = 0.75
    face_mask_coverage_bias: float = 0.0
    chest_patch_coverage_bias: float = 0.0
    paw_patch_coverage_bias: float = 0.0
    tail_tip_coverage_bias: float = 0.0


@dataclass(frozen=True)
class AppearanceGenome:
    genome_version: int
    species_profile_version: int
    seed: int
    macro: AppearanceMacro = field(default_factory=AppearanceMacro)
    proportions: AppearanceProportions = field(default_factory=AppearanceProportions)
    body_bias: BodyAppearance = field(default_factory=BodyAppearance)
    face: FaceAppearance = field(default_factory=FaceAppearance)
    appendages: AppendageAppearance = field(default_factory=AppendageAppearance)
    fur: FurAppearance = field(default_factory=FurAppearance)
    coat: CoatAppearance = field(default_factory=CoatAppearance)
    species_traits: Dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class EmbodimentProfile:
    primary_morphology: str = "biped"
    supported_morphologies: tuple[str, ...] = ("biped",)
    skeleton_profile_id: str = "humanoid_mixamo_v1"
    capability_profile_id: str = "default_biped_v1"


@dataclass(frozen=True)
class ElfieIdentity:
    elfie_id: str
    display_name: str
    species_id: str


@dataclass(frozen=True)
class ProfileProvenance:
    generator_version: str
    master_seed: int
    appearance_seed: int
    user_choices: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ElfieProfile:
    schema_version: int
    identity: ElfieIdentity
    appearance: AppearanceGenome
    provenance: ProfileProvenance
    embodiment: EmbodimentProfile = field(default_factory=EmbodimentProfile)
    # 迁移期先完整保存原 YAML 映射，避免类型化过程中丢失现有字段。
    personality: Dict[str, Any] = field(default_factory=dict)
    capabilities: Dict[str, Any] = field(default_factory=dict)
    system_limits: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.schema_version != PROFILE_SCHEMA_VERSION:
            raise ValueError(f"不支持 profile schema_version={self.schema_version}")
        if not self.identity.elfie_id.strip():
            raise ValueError("elfie_id 不能为空")
        if not self.identity.display_name.strip():
            raise ValueError("display_name 不能为空")
        if self.identity.species_id not in SUPPORTED_SPECIES:
            raise ValueError(
                f"不支持的 species_id={self.identity.species_id!r}，"
                f"可选: {', '.join(SUPPORTED_SPECIES)}"
            )
        if self.appearance.genome_version != 1:
            raise ValueError("当前只支持 appearance genome_version=1")
        if self.embodiment.primary_morphology not in SUPPORTED_MORPHOLOGIES:
            raise ValueError(
                f"primary_morphology 必须是 {', '.join(SUPPORTED_MORPHOLOGIES)}"
            )
        if not self.embodiment.supported_morphologies:
            raise ValueError("supported_morphologies 至少包含一个形态")
        for morphology in self.embodiment.supported_morphologies:
            if morphology not in SUPPORTED_MORPHOLOGIES:
                raise ValueError(f"不支持的 supported_morphologies 项: {morphology!r}")
        if (
            self.embodiment.primary_morphology
            not in self.embodiment.supported_morphologies
        ):
            raise ValueError("primary_morphology 必须包含在 supported_morphologies 中")
        for field_name in ("personality", "capabilities", "system_limits"):
            if not isinstance(getattr(self, field_name), dict):
                raise ValueError(f"{field_name} 必须是映射")
        from .species import get_species_profile  # noqa: PLC0415

        species = get_species_profile(self.identity.species_id)
        if self.appearance.species_profile_version != species.profile_version:
            raise ValueError("appearance 使用了不兼容的物种配置版本")
        coat = self.appearance.coat
        for value, allowed, field_name in (
            (coat.palette_id, species.palettes, "palette_id"),
            (coat.pattern_id, species.patterns, "pattern_id"),
            (coat.eye_color_id, species.eye_colors, "eye_color_id"),
            (coat.nose_color_id, species.nose_colors, "nose_color_id"),
        ):
            if value not in allowed:
                raise ValueError(
                    f"{field_name}={value!r} 不属于物种 {species.species_id} 的合法集合"
                )
        _validate_numeric_dataclass(self.appearance.macro, -2.0, 2.0)
        _validate_numeric_dataclass(self.appearance.proportions, -1.0, 1.0)
        _validate_numeric_dataclass(self.appearance.body_bias, -1.0, 1.0)
        _validate_numeric_dataclass(
            self.appearance.face,
            -1.0,
            1.0,
            unit_fields={"eyelid_fold"},
        )
        _validate_numeric_dataclass(
            self.appearance.appendages,
            -1.0,
            1.0,
            unit_fields={"ear_droop"},
        )
        _validate_numeric_dataclass(self.appearance.fur, -1.0, 1.0)
        _validate_numeric_dataclass(
            self.appearance.coat,
            -1.0,
            1.0,
            unit_fields={"pattern_symmetry"},
            ignored_fields={
                "palette_id",
                "pattern_id",
                "eye_color_id",
                "nose_color_id",
            },
        )
        for name, current in self.appearance.species_traits.items():
            if not isinstance(name, str) or not name:
                raise ValueError("species_traits 的键必须是非空字符串")
            if (
                not isinstance(current, (int, float))
                or not -1.0 <= float(current) <= 1.0
            ):
                raise ValueError(f"species_traits.{name} 必须在 [-1, 1] 内")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> ElfieProfile:
        identity_raw = _mapping(raw.get("identity"))
        appearance_raw = _mapping(raw.get("appearance"))
        embodiment_raw = _mapping(raw.get("embodiment"))
        if "supported_morphologies" in embodiment_raw:
            raw_morphologies = embodiment_raw.get("supported_morphologies")
            if isinstance(raw_morphologies, (list, tuple)):
                embodiment_raw["supported_morphologies"] = tuple(
                    str(item) for item in raw_morphologies
                )
        provenance_raw = _mapping(raw.get("provenance"))
        profile = cls(
            schema_version=int(raw.get("schema_version", PROFILE_SCHEMA_VERSION)),
            identity=_construct(ElfieIdentity, identity_raw),
            appearance=AppearanceGenome(
                genome_version=int(appearance_raw.get("genome_version", 1)),
                species_profile_version=int(
                    appearance_raw.get("species_profile_version", 1)
                ),
                seed=int(appearance_raw.get("seed", 0)),
                macro=_construct(
                    AppearanceMacro, _mapping(appearance_raw.get("macro"))
                ),
                proportions=_construct(
                    AppearanceProportions,
                    _mapping(appearance_raw.get("proportions")),
                ),
                body_bias=_construct(
                    BodyAppearance,
                    _mapping(appearance_raw.get("body_bias")),
                ),
                face=_construct(FaceAppearance, _mapping(appearance_raw.get("face"))),
                appendages=_construct(
                    AppendageAppearance,
                    _mapping(appearance_raw.get("appendages")),
                ),
                fur=_construct(FurAppearance, _mapping(appearance_raw.get("fur"))),
                coat=_construct(CoatAppearance, _mapping(appearance_raw.get("coat"))),
                species_traits={
                    str(key): float(value)
                    for key, value in _mapping(
                        appearance_raw.get("species_traits")
                    ).items()
                },
            ),
            embodiment=_construct(EmbodimentProfile, embodiment_raw),
            provenance=_construct(ProfileProvenance, provenance_raw),
            personality=_mapping(raw.get("personality")),
            capabilities=_mapping(raw.get("capabilities")),
            system_limits=_mapping(raw.get("system_limits")),
        )
        profile.validate()
        return profile


T = TypeVar("T")


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _construct(model: Type[T], raw: Dict[str, Any]) -> T:
    allowed = {item.name for item in fields(model)}
    return model(**{key: value for key, value in raw.items() if key in allowed})


def _validate_numeric_dataclass(
    value: Any,
    minimum: float,
    maximum: float,
    *,
    unit_fields: set[str] | None = None,
    ignored_fields: set[str] | None = None,
) -> None:
    unit_fields = unit_fields or set()
    ignored_fields = ignored_fields or set()
    for item in fields(value):
        if item.name in ignored_fields:
            continue
        current = getattr(value, item.name)
        if not isinstance(current, (int, float)):
            raise ValueError(f"{item.name} 必须是数值")
        field_minimum, field_maximum = (
            (0.0, 1.0) if item.name in unit_fields else (minimum, maximum)
        )
        if not field_minimum <= float(current) <= field_maximum:
            raise ValueError(
                f"{item.name}={current} 超出范围 [{field_minimum}, {field_maximum}]"
            )
