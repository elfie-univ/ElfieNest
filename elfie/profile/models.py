"""精灵视觉身份的类型化数据模型。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, replace
from typing import TYPE_CHECKING, Any, Dict, Type, TypeVar, cast

from .species_registry import SUPPORTED_SPECIES

if TYPE_CHECKING:
    from .species_registry import SpeciesCatalog

PROFILE_SCHEMA_VERSION = 1
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
class RegionAccent:
    """One explicit local color accent carried by the immutable genome."""

    region_id: str
    color_id: str
    grade_id: str = "L1"
    intensity: float = 0.8


@dataclass(frozen=True)
class CoatAppearance:
    palette_id: str = "default"
    pattern_id: str = "solid"
    pattern_layout_id: str = ""
    primary_color_id: str = ""
    secondary_color_id: str = ""
    accent_color_id: str = ""
    face_mask_color_id: str = ""
    marking_color_id: str = ""
    marking_id: str = "none"
    marking_placement: str = "none"
    marking_scale: float = 0.9
    marking_intensity: float = 0.9
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
    region_recipe_id: str = "base"
    region_accents: tuple[RegionAccent, ...] = ()


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
class ElfieOrigin:
    """Immutable origin and arrival facts owned by the Elfie Profile."""

    home_world_id: str = "elfaria"
    home_region_id: str = "mistyville"
    birth_at: str | None = None
    arrival_mode: str = "earth_gateway"
    arrival_base_id: str = "elfie_nest"


@dataclass(frozen=True)
class ElfieIdentity:
    elfie_id: str
    display_name: str
    species_id: str
    origin: ElfieOrigin = field(default_factory=ElfieOrigin)


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

    def validate(self, *, catalog: SpeciesCatalog | None = None) -> None:
        if self.schema_version != PROFILE_SCHEMA_VERSION:
            raise ValueError(f"不支持 profile schema_version={self.schema_version}")
        if not self.identity.elfie_id.strip():
            raise ValueError("elfie_id 不能为空")
        if not self.identity.display_name.strip():
            raise ValueError("display_name 不能为空")
        try:
            if catalog is None:
                if self.identity.species_id not in SUPPORTED_SPECIES:
                    raise ValueError
            else:
                catalog.definition(self.identity.species_id)
        except ValueError as error:
            available = (
                SUPPORTED_SPECIES if catalog is None else catalog.supported_species
            )
            raise ValueError(
                f"不支持的 species_id={self.identity.species_id!r}，"
                f"可选: {', '.join(available)}"
            ) from error
        origin = self.identity.origin
        for field_name in (
            "home_world_id",
            "home_region_id",
            "arrival_mode",
            "arrival_base_id",
        ):
            if not getattr(origin, field_name).strip():
                raise ValueError(f"origin.{field_name} 不能为空")
        if origin.home_world_id != "elfaria":
            raise ValueError("当前 Profile 只支持 Elfaria 作为原生世界")
        if self.appearance.genome_version not in (1, 2):
            raise ValueError("当前只支持 appearance genome_version=1/2")
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
        if catalog is None:
            from .species import get_species_profile  # noqa: PLC0415

            species = get_species_profile(self.identity.species_id)
        else:
            species = catalog.definition(self.identity.species_id).appearance
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
        pattern_layouts = species.pattern_layouts.get(coat.pattern_id, ())
        if coat.pattern_layout_id and (
            not pattern_layouts or coat.pattern_layout_id not in pattern_layouts
        ):
            raise ValueError(
                f"pattern_layout_id={coat.pattern_layout_id!r} 不属于物种 "
                f"{species.species_id} 的花纹布局"
            )
        if coat.marking_id not in species.markings:
            raise ValueError(
                f"marking_id={coat.marking_id!r} 不属于物种 "
                f"{species.species_id} 的合法标记"
            )
        if coat.marking_placement not in species.marking_placements:
            raise ValueError(
                f"marking_placement={coat.marking_placement!r} 不属于物种 "
                f"{species.species_id} 的合法标记位置"
            )
        if coat.region_recipe_id not in species.region_recipes:
            raise ValueError(
                f"region_recipe_id={coat.region_recipe_id!r} 不属于物种 "
                f"{species.species_id} 的合法区域配方"
            )
        if len(coat.region_accents) > species.max_region_accents:
            raise ValueError(
                f"区域特异色最多允许 {species.max_region_accents} 个，"
                f"实际为 {len(coat.region_accents)} 个"
            )
        accent_regions = [accent.region_id for accent in coat.region_accents]
        if len(accent_regions) != len(set(accent_regions)):
            raise ValueError("区域特异色不能重复使用同一个区域")
        recipe = species.region_recipes[coat.region_recipe_id]
        expected_accents = tuple(
            (
                accent.region_id,
                accent.color_id,
                accent.grade_id,
                round(float(accent.intensity), 6),
            )
            for accent in recipe.accents
        )
        actual_accents = tuple(
            (
                accent.region_id,
                accent.color_id,
                accent.grade_id,
                round(float(accent.intensity), 6),
            )
            for accent in coat.region_accents
        )
        if actual_accents != expected_accents:
            raise ValueError("region_accents 必须与物种配置中的区域配方完全一致")
        for accent in coat.region_accents:
            rule = species.region_rules.get(accent.region_id)
            if rule is None or rule.mode not in ("color-only", "color-or-mark"):
                raise ValueError(f"区域 {accent.region_id!r} 不允许配色")
            if accent.color_id not in rule.allowed_colors:
                raise ValueError(
                    f"区域 {accent.region_id!r} 不允许颜色 {accent.color_id!r}"
                )
            if accent.grade_id not in rule.allowed_grades:
                raise ValueError(
                    f"区域 {accent.region_id!r} 不允许色阶 {accent.grade_id!r}"
                )
            if not 0.0 <= float(accent.intensity) <= 1.0:
                raise ValueError(f"区域 {accent.region_id!r} 的强度必须在 [0, 1] 内")
        marking_rule = species.marking_rules.get(coat.marking_id)
        if marking_rule is None:
            raise ValueError(f"缺少标记 {coat.marking_id!r} 的兼容规则")
        if coat.marking_placement not in marking_rule.placements:
            raise ValueError(
                f"标记 {coat.marking_id!r} 不允许放在 {coat.marking_placement!r}"
            )
        if coat.marking_id != "none" and coat.marking_placement == "none":
            raise ValueError("启用局部标记时必须提供非 none 的位置")
        if coat.marking_id == "none" and coat.marking_placement != "none":
            raise ValueError("没有局部标记时位置必须为 none")
        if (
            coat.marking_id != "none"
            and coat.marking_color_id not in marking_rule.allowed_colors
        ):
            raise ValueError(
                f"标记 {coat.marking_id!r} 不允许颜色 {coat.marking_color_id!r}"
            )
        color_ids = (
            coat.primary_color_id,
            coat.secondary_color_id,
            coat.accent_color_id,
            coat.face_mask_color_id,
            coat.marking_color_id,
        )
        for color_id in color_ids:
            if color_id and color_id not in species.palettes:
                raise ValueError(
                    f"外观颜色槽 {color_id!r} 不属于物种 {species.species_id} 的颜色集合"
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
                "pattern_layout_id",
                "primary_color_id",
                "secondary_color_id",
                "accent_color_id",
                "face_mask_color_id",
                "marking_color_id",
                "marking_id",
                "marking_placement",
                "eye_color_id",
                "nose_color_id",
                "region_recipe_id",
                "region_accents",
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
        identity_fields = _construct(ElfieIdentity, identity_raw)
        identity_fields = replace(
            identity_fields,
            origin=_construct(ElfieOrigin, _mapping(identity_raw.get("origin"))),
        )
        profile = cls(
            schema_version=int(raw.get("schema_version", PROFILE_SCHEMA_VERSION)),
            identity=identity_fields,
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
                coat=_coat_from_dict(_mapping(appearance_raw.get("coat"))),
                species_traits={
                    str(key): float(value)
                    for key, value in _mapping(
                        appearance_raw.get("species_traits")
                    ).items()
                },
            ),
            embodiment=_construct(EmbodimentProfile, embodiment_raw),
            provenance=_construct(ProfileProvenance, provenance_raw),
        )
        profile.validate()
        return profile


T = TypeVar("T")


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _construct(model: Type[T], raw: Dict[str, Any]) -> T:
    allowed = {item.name for item in fields(cast(Any, model))}
    return model(**{key: value for key, value in raw.items() if key in allowed})


def _coat_from_dict(raw: Dict[str, Any]) -> CoatAppearance:
    values = dict(raw)
    accents = values.get("region_accents", ())
    if isinstance(accents, (list, tuple)):
        values["region_accents"] = tuple(
            _construct(RegionAccent, item) for item in accents if isinstance(item, dict)
        )
    else:
        values["region_accents"] = ()
    return _construct(CoatAppearance, values)


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
