"""精灵视觉身份的类型化数据模型。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import TYPE_CHECKING, Any, Dict, Optional, Type, TypeVar, cast

from pydantic import Field, StringConstraints
from typing_extensions import Annotated

from elfie.message_types import FrozenContractModel, UTCDateTime

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
    macro: AppearanceMacro = field(default_factory=AppearanceMacro)
    proportions: AppearanceProportions = field(default_factory=AppearanceProportions)
    body_bias: BodyAppearance = field(default_factory=BodyAppearance)
    face: FaceAppearance = field(default_factory=FaceAppearance)
    appendages: AppendageAppearance = field(default_factory=AppendageAppearance)
    fur: FurAppearance = field(default_factory=FurAppearance)
    coat: CoatAppearance = field(default_factory=CoatAppearance)
    species_traits: Dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ElfieOrigin:
    """Stable personal-origin and Earth-age values exposed by Profile.

    This is deliberately narrower than a life history.  It identifies where
    the individual says they come from and fixes the age anchor used by
    external projections; routes, training, arrival events and world facts
    belong to Memory or to the one-time Genesis transaction.
    """

    origin_place_id: str = "unknown-origin"
    origin_place_label: str = "未知来源"
    age_years: int | None = None
    age_anchor_at: str | None = None

    def __post_init__(self) -> None:
        """Normalize the two stable origin labels before validation."""

        place_id = self.origin_place_id.strip()
        place_label = (self.origin_place_label or place_id).strip()
        object.__setattr__(self, "origin_place_id", place_id)
        object.__setattr__(self, "origin_place_label", place_label)


@dataclass(frozen=True)
class ElfieIdentity:
    elfie_id: str
    display_name: str
    species_id: str
    origin: ElfieOrigin = field(default_factory=ElfieOrigin)
    gender: str | None = None


@dataclass(frozen=True)
class ElfieProfile:
    """Frozen external identity dossier.

    Profile is intentionally not a Genesis ledger.  Only stable identity,
    personal-origin labels, age anchor and final virtual appearance live here.
    Personality, capabilities, world knowledge, relationships, stories and
    all generation inputs are owned elsewhere.
    """

    schema_version: int
    identity: ElfieIdentity
    appearance: AppearanceGenome

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
        if not origin.origin_place_id.strip():
            raise ValueError("origin.origin_place_id 不能为空")
        if not origin.origin_place_label.strip():
            raise ValueError("origin.origin_place_label 不能为空")
        if origin.age_years is not None and (
            isinstance(origin.age_years, bool) or origin.age_years < 1
        ):
            raise ValueError("origin.age_years 必须为正整数")
        if origin.age_anchor_at is not None and not origin.age_anchor_at.strip():
            raise ValueError("origin.age_anchor_at 不能为空")
        if self.identity.gender is not None and not self.identity.gender.strip():
            raise ValueError("identity.gender 不能为空")
        if self.appearance.genome_version not in (1, 2):
            raise ValueError("当前只支持 appearance genome_version=1/2")
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
        """Serialize only the public, immutable Profile contract.

        In particular this method must never make a saved Profile a Genesis
        replay record.  ``seed``, provenance, embodiment/capability, world
        facts, arrival/training details and personality are intentionally not
        emitted here.
        """

        self.validate()
        origin = self.identity.origin
        identity: Dict[str, Any] = {
            "elfie_id": self.identity.elfie_id,
            "display_name": self.identity.display_name,
            "species_id": self.identity.species_id,
            "origin": {
                "place_id": origin.origin_place_id,
                "place_label": origin.origin_place_label,
                "age_years": origin.age_years,
                "age_anchor_at": origin.age_anchor_at,
            },
        }
        if self.identity.gender is not None:
            identity["gender"] = self.identity.gender
        appearance = asdict(self.appearance)
        return {
            "schema_version": self.schema_version,
            "identity": identity,
            "appearance": appearance,
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> ElfieProfile:
        if not isinstance(raw, dict):
            raise ValueError("Profile 根节点必须是对象")
        _reject_keys(raw, {"schema_version", "identity", "appearance"}, "Profile")
        identity_raw = _mapping(raw.get("identity"))
        appearance_raw = _mapping(raw.get("appearance"))
        _reject_keys(
            identity_raw,
            {"elfie_id", "display_name", "species_id", "gender", "origin"},
            "Profile.identity",
        )
        origin_raw = _mapping(identity_raw.get("origin"))
        _reject_keys(
            origin_raw,
            {"place_id", "place_label", "age_years", "age_anchor_at"},
            "Profile.identity.origin",
        )
        _reject_keys(
            appearance_raw,
            {
                "genome_version",
                "species_profile_version",
                "macro",
                "proportions",
                "body_bias",
                "face",
                "appendages",
                "fur",
                "coat",
                "species_traits",
            },
            "Profile.appearance",
        )
        place_id = str(origin_raw.get("place_id", "")).strip()
        place_label = str(origin_raw.get("place_label", place_id)).strip()
        age_years = origin_raw.get("age_years")
        if age_years is not None:
            age_years = int(age_years)
        age_anchor = origin_raw.get("age_anchor_at")
        identity_fields = ElfieIdentity(
            elfie_id=str(identity_raw.get("elfie_id", "")),
            display_name=str(identity_raw.get("display_name", "")),
            species_id=str(identity_raw.get("species_id", "")),
            gender=(
                None
                if identity_raw.get("gender") is None
                else str(identity_raw.get("gender"))
            ),
            origin=ElfieOrigin(
                origin_place_id=place_id,
                origin_place_label=place_label,
                age_years=age_years,
                age_anchor_at=None if age_anchor is None else str(age_anchor),
            ),
        )
        profile = cls(
            schema_version=int(raw.get("schema_version", PROFILE_SCHEMA_VERSION)),
            identity=identity_fields,
            appearance=AppearanceGenome(
                genome_version=int(appearance_raw.get("genome_version", 1)),
                species_profile_version=int(
                    appearance_raw.get("species_profile_version", 1)
                ),
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
        )
        profile.validate()
        return profile


T = TypeVar("T")


_ProfileText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=512, pattern=r".*\S.*"),
]
_ProfileOptionalText = Optional[_ProfileText]


class ProfileDossier(FrozenContractModel):
    """Read-only observer projection of the Profile-owned public identity."""

    revision: int = Field(strict=True, ge=1)
    captured_at: UTCDateTime
    elfie_id: _ProfileText
    display_name: _ProfileText
    species_id: _ProfileText
    species_name: _ProfileText
    species_shape: _ProfileText
    gender: _ProfileOptionalText = None
    age_years: Optional[int] = Field(default=None, strict=True, ge=1)
    origin_place_id: _ProfileText
    origin_place_label: _ProfileText
    appearance_genome_version: int = Field(strict=True, ge=1)


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _reject_keys(raw: Dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ValueError(
            f"{label} 包含不属于当前 Profile 契约的字段: {', '.join(unknown)}"
        )


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
