"""Bundled species catalog and package loader.

The catalog is a registered bundled configuration document. Member files are
loaded only through the fixed ``config/species/<package>/`` layout; callers do
not provide arbitrary paths. Semantic validation happens here before the
typed catalog crosses into Profile, Genesis or Adoption.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Mapping, cast

from elfie.profile import (
    APPEARANCE_REGION_IDS,
    SPECIES_CANON_VERSION,
    AppearanceMarkingRule,
    AppearanceRegionRecipe,
    AppearanceRegionRule,
    CorrelationWeights,
    Distribution,
    RegionAccentSpec,
    ScaleRange,
    SpeciesAppearanceProfile,
    SpeciesCanon,
    SpeciesCatalog,
    SpeciesDefinition,
    SpeciesGenesisProfile,
    SpeciesPresentationImages,
    SpeciesStatus,
)

from .config_store import ConfigStoreError, read_yaml_mapping
from .documents import (
    BundledConfigSource,
    ConfigDocumentError,
    ConfigDocumentId,
    resolve_bundled_config_root,
)

_PACKAGE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_STAGES = ("youth", "young_adult", "mature", "elder")
_GENESIS_TRAITS = 5
_MAX_AGE_MONTHS = 240
_REQUIRED_PROPORTION_SCALES = (
    "HeadScale",
    "NeckLength",
    "ArmLength",
    "LegLength",
    "ShoulderWidth",
    "HandScale",
    "PawScale",
    "TailLength",
    "EyeScale",
    "EyeSpacing",
    "EyeHeight",
)
_REQUIRED_SHAPE_CORRELATIONS = (
    "Body_ChestFullness",
    "Body_WaistWidth",
    "Body_BellyDepth",
    "Body_HipWidth",
    "Body_HipDepth",
    "Body_ArmThickness",
    "Body_LegThickness",
    "Body_NeckThickness",
    "Body_PawFullness",
    "Face_CheekFullness",
    "Face_LowerFullness",
)
_REQUIRED_SEMANTIC_CONTROLS = ("stature", "build", "face", "signature")


class SpeciesCatalogError(ConfigDocumentError):
    """The bundled species catalog or one required member is invalid."""


class BundledSpeciesCatalogSource:
    """Load the immutable catalog from one bundled resource root."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = resolve_bundled_config_root(root)

    def load(self) -> SpeciesCatalog:
        try:
            loaded = BundledConfigSource(self.root).load(
                ConfigDocumentId.SPECIES_CATALOG
            )
        except ConfigDocumentError as error:
            raise SpeciesCatalogError(str(error)) from error
        document = loaded.document
        raw_species = document.get("species")
        if not isinstance(raw_species, list):
            raise SpeciesCatalogError("species.catalog.yaml 的 species 必须是数组")

        definitions: list[SpeciesDefinition] = []
        for index, raw_entry in enumerate(raw_species):
            try:
                entry = _object(raw_entry, f"species[{index}]")
                definition = self._load_definition(entry)
            except (OSError, ConfigStoreError, TypeError, ValueError) as error:
                status = (
                    raw_entry.get("status") if isinstance(raw_entry, Mapping) else None
                )
                if status == "draft":
                    # Draft members are deliberately fail-closed and omitted
                    # from runtime projections until their package is complete.
                    continue
                raise SpeciesCatalogError(
                    f"物种配置无效 species[{index}]: {error}"
                ) from error
            definitions.append(definition)

        definitions.sort(key=lambda item: item.sort_order)
        catalog = SpeciesCatalog(
            catalog_version=_string(document, "catalog_version"),
            appearance_protocol_version=_string(
                document, "appearance_protocol_version"
            ),
            definitions=tuple(definitions),
            digest=_catalog_digest(self.root / "species"),
        )
        _validate_catalog(catalog)
        return catalog

    def _load_definition(self, entry: Mapping[str, Any]) -> SpeciesDefinition:
        species_id = _package_id(entry, "species_id")
        package = _package_id(entry, "package")
        if species_id != entry.get("species_id"):
            raise ValueError("species_id 无效")
        package_root = self.root / "species" / package
        species_document = _read_member(package_root / "species.yaml")
        appearance_document = _read_member(package_root / "appearance.yaml")
        genesis_document = _read_optional_member(package_root / "genesis.yaml")

        expected_id = _string(species_document, "technical_species_id")
        if expected_id != species_id:
            raise ValueError("species.yaml technical_species_id 与 catalog 不一致")
        appearance = _appearance_profile(species_id, appearance_document)
        canon = SpeciesCanon(
            canon_id=_string(species_document, "canon_id"),
            display_name=_string(species_document, "display_name"),
            display_name_zh=_string(species_document, "display_name_zh"),
            earth_shape_label=_string(species_document, "earth_shape_label"),
            technical_species_id=species_id,
            sort_order=_nonnegative_int(entry, "sort_order"),
            common_sensory_biases=_string_tuple(
                species_document, "common_sensory_biases"
            ),
            common_knowledge=_string_tuple(species_document, "common_knowledge"),
            earth_first_contact_cues=_string_tuple(
                species_document, "earth_first_contact_cues"
            ),
            canon_version=str(
                species_document.get("canon_version", SPECIES_CANON_VERSION)
            ),
        )
        images = self._presentation_images(package_root, species_document, entry)
        genesis = _genesis_profile(genesis_document) if genesis_document else None
        status = _status(entry)
        canon_id = _string(entry, "canon_id")
        if canon_id != canon.canon_id:
            raise ValueError("catalog canon_id 与 species.yaml 不一致")
        if status in ("published", "retired") and (images is None or genesis is None):
            raise ValueError("已发布或已退役物种必须同时具备两张 PNG 和 Genesis 配置")
        return SpeciesDefinition(
            species_id=species_id,
            canon_id=canon_id,
            display_name=canon.display_name,
            display_name_zh=canon.display_name_zh,
            earth_shape_label=canon.earth_shape_label,
            config_package_id=package,
            godot_package_id=_package_id(species_document, "godot_package_id"),
            sort_order=canon.sort_order,
            status=status,
            definition_version=_string(entry, "definition_version"),
            appearance_profile_version=appearance.profile_version,
            appearance=appearance,
            canon=canon,
            presentation_images=images,
            genesis=genesis,
        )

    def _presentation_images(
        self,
        package_root: Path,
        species_document: Mapping[str, Any],
        entry: Mapping[str, Any],
    ) -> SpeciesPresentationImages | None:
        raw = species_document.get("presentation_images")
        if not isinstance(raw, Mapping):
            if _status(entry) == "draft":
                return None
            raise ValueError("缺少 presentation_images")
        headshot = _relative_png(raw, "headshot")
        full_body = _relative_png(raw, "full_body")
        for relative in (headshot, full_body):
            path = (package_root / relative).resolve()
            try:
                path.relative_to(package_root.resolve())
            except ValueError as error:
                raise ValueError(f"物种图片越界: {relative}") from error
            if not path.is_file():
                raise ValueError(f"物种图片缺失: {relative}")
            if path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
                raise ValueError(f"物种图片不是有效 PNG: {relative}")
        if (
            len(
                {
                    (package_root / relative).read_bytes()
                    for relative in (headshot, full_body)
                }
            )
            != 2
        ):
            raise ValueError("物种 headshot 与 full_body 不得使用同一张图片")
        return SpeciesPresentationImages(headshot=headshot, full_body=full_body)


def load_species_catalog(*, root: Path | None = None) -> SpeciesCatalog:
    """Load and validate the one bundled species catalog."""

    return BundledSpeciesCatalogSource(root).load()


def load_and_configure_species_catalog(*, root: Path | None = None) -> SpeciesCatalog:
    """Load the bundled catalog and inject it at the domain composition boundary."""

    catalog = load_species_catalog(root=root)
    from elfie.profile import configure_species_catalog  # noqa: PLC0415

    configure_species_catalog(catalog)
    return catalog


def species_asset_path(
    root: Path,
    definition: SpeciesDefinition,
    kind: str,
) -> Path:
    """Resolve one already-validated PNG asset by its closed kind."""

    images = definition.presentation_images
    if images is None or kind not in ("headshot", "full-body"):
        raise SpeciesCatalogError("物种图片类型无效或物种没有图片")
    relative = images.headshot if kind == "headshot" else images.full_body
    package_root = (root / "species" / definition.config_package_id).resolve()
    path = (package_root / relative).resolve()
    try:
        path.relative_to(package_root)
    except ValueError as error:
        raise SpeciesCatalogError("物种图片路径越界") from error
    if not path.is_file():
        raise SpeciesCatalogError("物种图片不存在")
    return path


def _appearance_profile(
    species_id: str,
    document: Mapping[str, Any],
) -> SpeciesAppearanceProfile:
    profile_version = _positive_int(document, "profile_version")
    has_region_appearance = profile_version >= 2
    palettes = _string_tuple(document, "palettes")
    patterns = _string_tuple(document, "patterns")
    markings = _string_tuple_or_default(document.get("markings"), ("none",), "markings")
    marking_placements = _string_tuple_or_default(
        document.get("marking_placements"), ("none",), "marking_placements"
    )
    region_rules = (
        _region_rules(document.get("region_rules"), palettes)
        if has_region_appearance
        else {}
    )
    region_recipes = (
        _region_recipes(
            document.get("region_recipes"),
            region_rules=region_rules,
            palettes=palettes,
        )
        if has_region_appearance
        else {}
    )
    marking_rules = (
        _marking_rules(
            document.get("marking_rules"),
            markings=markings,
            marking_placements=marking_placements,
            palettes=palettes,
        )
        if has_region_appearance
        else {"none": AppearanceMarkingRule(("none",), palettes)}
    )
    profile = SpeciesAppearanceProfile(
        species_id=species_id,
        profile_version=profile_version,
        stature_scale=_scale(document, "stature_scale"),
        build_scale=_scale(document, "build_scale"),
        build_weights=_weights(document, "build_weights"),
        palettes=palettes,
        patterns=patterns,
        eye_colors=_string_tuple(document, "eye_colors"),
        nose_colors=_string_tuple(document, "nose_colors"),
        pattern_color_slots=_pattern_color_slots(
            document.get("pattern_color_slots"),
            patterns,
        ),
        pattern_layouts=_pattern_layouts(
            document.get("pattern_layouts"),
            patterns,
        ),
        markings=markings,
        marking_placements=marking_placements,
        supported_controls=_string_tuple(document, "supported_controls"),
        control_options=_control_options(document.get("control_options")),
        control_ranges=_ranges(document.get("control_ranges"), "control_ranges"),
        proportion_scales=_ranges(
            document.get("proportion_scales"), "proportion_scales", optional=True
        ),
        shape_correlations=_correlations(
            document.get("shape_correlations"), "shape_correlations"
        ),
        distributions=_distributions(document.get("distributions")),
        species_traits=_string_tuple(document, "species_traits"),
        region_rules=region_rules,
        region_recipes=region_recipes,
        region_recipe_order=_ordered_subset(
            document.get("region_recipe_order"),
            region_recipes,
            "region_recipe_order",
        ),
        marking_rules=marking_rules,
        batch_palette_order=_ordered_subset(
            document.get("batch_palette_order"), palettes, "batch_palette_order"
        ),
        batch_recipe_order=_ordered_subset(
            document.get("batch_recipe_order"),
            tuple(region_recipes),
            "batch_recipe_order",
        ),
        batch_marking_order=_ordered_sequence(
            document.get("batch_marking_order"),
            markings,
            "batch_marking_order",
        ),
        max_region_accents=(
            _bounded_count(
                document.get("max_region_accents", 2),
                "max_region_accents",
                0,
                3,
            )
            if has_region_appearance
            else 0
        ),
        max_marks=(
            _bounded_count(document.get("max_marks", 1), "max_marks", 0, 1)
            if has_region_appearance
            else 0
        ),
        max_forehead_marks=(
            _bounded_count(
                document.get("max_forehead_marks", 1),
                "max_forehead_marks",
                0,
                1,
            )
            if has_region_appearance
            else 0
        ),
    )
    missing_proportions = set(_REQUIRED_PROPORTION_SCALES).difference(
        profile.proportion_scales
    )
    missing_shapes = set(_REQUIRED_SHAPE_CORRELATIONS).difference(
        profile.shape_correlations
    )
    missing_controls = set(_REQUIRED_SEMANTIC_CONTROLS).difference(
        profile.supported_controls
    )
    missing_control_ranges = set(_REQUIRED_SEMANTIC_CONTROLS).difference(
        profile.control_ranges
    )
    missing_control_options = set(_REQUIRED_SEMANTIC_CONTROLS).difference(
        profile.control_options
    )
    if (
        missing_proportions
        or missing_shapes
        or missing_controls
        or missing_control_ranges
        or missing_control_options
        or "ear_droop" not in profile.distributions
    ):
        raise ValueError(
            f"{species_id} appearance 缺少必要控制: "
            f"proportion={sorted(missing_proportions)} "
            f"shape={sorted(missing_shapes)} "
            f"controls={sorted(missing_controls)} "
            f"control_ranges={sorted(missing_control_ranges)} "
            f"control_options={sorted(missing_control_options)} "
            f"ear_droop={'ear_droop' not in profile.distributions}"
        )
    return profile


def _control_options(value: Any) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, Mapping):
        raise ValueError("control_options 必须是对象")
    result: dict[str, tuple[str, ...]] = {}
    for control_id, raw_options in value.items():
        if not isinstance(control_id, str) or not control_id.strip():
            raise ValueError("control_options 包含无效控制项")
        options = _tuple_value(raw_options, f"control_options.{control_id}")
        if not options or len(set(options)) != len(options):
            raise ValueError(f"control_options.{control_id} 必须是非空且不重复的数组")
        result[control_id] = options
    return result


def _region_rules(
    value: Any,
    palettes: tuple[str, ...],
) -> Mapping[str, AppearanceRegionRule]:
    mapping = _object(value, "region_rules")
    unknown = set(mapping) - set(APPEARANCE_REGION_IDS)
    if unknown:
        raise ValueError("region_rules 包含未知区域: " + ", ".join(sorted(unknown)))
    result: dict[str, AppearanceRegionRule] = {}
    valid_modes = {"color-only", "color-or-mark", "mark-only", "disabled"}
    for region_id in APPEARANCE_REGION_IDS:
        item = _object(mapping.get(region_id), f"region_rules.{region_id}")
        mode = _string(item, "mode")
        if mode not in valid_modes:
            raise ValueError(f"region_rules.{region_id}.mode 无效: {mode}")
        colors = _string_tuple_maybe_empty(
            item.get("allowed_colors", ()), f"region_rules.{region_id}.allowed_colors"
        )
        grades = _string_tuple_maybe_empty(
            item.get("allowed_grades", ()), f"region_rules.{region_id}.allowed_grades"
        )
        if mode in ("color-only", "color-or-mark") and not colors:
            raise ValueError(f"region_rules.{region_id} 必须声明 allowed_colors")
        if mode in ("color-only", "color-or-mark") and not grades:
            raise ValueError(f"region_rules.{region_id} 必须声明 allowed_grades")
        if set(colors) - set(palettes):
            raise ValueError(f"region_rules.{region_id} 使用了未声明的颜色")
        source_mid_luma = _number(
            item.get("source_mid_luma"), f"region_rules.{region_id}.source_mid_luma"
        )
        default_intensity = _number(
            item.get("default_intensity", 0.8),
            f"region_rules.{region_id}.default_intensity",
        )
        if not 0.05 <= source_mid_luma <= 1.0:
            raise ValueError(f"region_rules.{region_id}.source_mid_luma 超出范围")
        if not 0.0 <= default_intensity <= 1.0:
            raise ValueError(f"region_rules.{region_id}.default_intensity 超出范围")
        result[region_id] = AppearanceRegionRule(
            mode=mode,
            allowed_colors=colors,
            allowed_grades=grades,
            source_mid_luma=source_mid_luma,
            default_intensity=default_intensity,
        )
    return result


def _region_recipes(
    value: Any,
    *,
    region_rules: Mapping[str, AppearanceRegionRule],
    palettes: tuple[str, ...],
) -> Mapping[str, AppearanceRegionRecipe]:
    mapping = _object(value, "region_recipes")
    if "base" not in mapping:
        raise ValueError("region_recipes 必须包含 base 配方")
    result: dict[str, AppearanceRegionRecipe] = {}
    for recipe_id, raw in mapping.items():
        if not isinstance(recipe_id, str) or not recipe_id.strip():
            raise ValueError("region_recipes 的键必须是非空字符串")
        item = _object(raw, f"region_recipes.{recipe_id}")
        raw_accents = item.get("accents", ())
        if not isinstance(raw_accents, (list, tuple)) or len(raw_accents) > 2:
            raise ValueError(f"region_recipes.{recipe_id}.accents 最多允许两个区域")
        accents: list[RegionAccentSpec] = []
        seen: set[str] = set()
        for index, raw_accent in enumerate(raw_accents):
            accent = _object(raw_accent, f"region_recipes.{recipe_id}.accents[{index}]")
            region_id = _string(accent, "region_id")
            color_id = _string(accent, "color_id")
            grade_id = _string(accent, "grade_id")
            intensity = _number(
                accent.get("intensity", 0.8),
                f"region_recipes.{recipe_id}.accents[{index}].intensity",
            )
            rule = region_rules.get(region_id)
            if rule is None or rule.mode not in ("color-only", "color-or-mark"):
                raise ValueError(f"区域 {region_id!r} 不允许进入颜色配方")
            if region_id in seen:
                raise ValueError(f"region_recipes.{recipe_id} 重复区域 {region_id}")
            if color_id not in palettes or color_id not in rule.allowed_colors:
                raise ValueError(
                    f"region_recipes.{recipe_id} 的颜色 {color_id!r} 不在区域白名单"
                )
            if grade_id not in rule.allowed_grades:
                raise ValueError(
                    f"region_recipes.{recipe_id} 的色阶 {grade_id!r} 不在区域白名单"
                )
            if not 0.0 <= intensity <= 1.0:
                raise ValueError(f"region_recipes.{recipe_id} 的强度超出范围")
            seen.add(region_id)
            accents.append(RegionAccentSpec(region_id, color_id, grade_id, intensity))
        result[recipe_id] = AppearanceRegionRecipe(recipe_id, tuple(accents))
    return result


def _marking_rules(
    value: Any,
    *,
    markings: tuple[str, ...],
    marking_placements: tuple[str, ...],
    palettes: tuple[str, ...],
) -> Mapping[str, AppearanceMarkingRule]:
    mapping = _object(value, "marking_rules")
    unknown = set(mapping) - set(markings)
    missing = set(markings) - set(mapping)
    if unknown or missing:
        raise ValueError(
            "marking_rules 必须与 markings 一一对应; "
            f"unknown={sorted(unknown)} missing={sorted(missing)}"
        )
    result: dict[str, AppearanceMarkingRule] = {}
    for marking_id in markings:
        item = _object(mapping.get(marking_id), f"marking_rules.{marking_id}")
        placements = _string_tuple_maybe_empty(
            item.get("placements", ()), f"marking_rules.{marking_id}.placements"
        )
        colors = _string_tuple_maybe_empty(
            item.get("allowed_colors", ()),
            f"marking_rules.{marking_id}.allowed_colors",
        )
        if marking_id == "none":
            placements = ("none",)
            colors = palettes
        if not placements:
            raise ValueError(f"marking_rules.{marking_id} 必须至少允许一个位置")
        if set(placements) - set(marking_placements):
            raise ValueError(f"marking_rules.{marking_id} 使用了未声明的位置")
        if set(colors) - set(palettes):
            raise ValueError(f"marking_rules.{marking_id} 使用了未声明的颜色")
        result[marking_id] = AppearanceMarkingRule(placements, colors)
    return result


def _ordered_subset(value: Any, allowed: Any, label: str) -> tuple[str, ...]:
    allowed_values = (
        tuple(allowed) if not isinstance(allowed, Mapping) else tuple(allowed)
    )
    selected = allowed_values if value is None else _tuple_value(value, label)
    if len(set(selected)) != len(selected):
        raise ValueError(f"{label} 不得重复")
    unknown = set(selected) - set(allowed_values)
    if unknown:
        raise ValueError(f"{label} 包含未声明 ID: " + ", ".join(sorted(unknown)))
    return selected


def _ordered_sequence(value: Any, allowed: Any, label: str) -> tuple[str, ...]:
    allowed_values = (
        tuple(allowed) if not isinstance(allowed, Mapping) else tuple(allowed)
    )
    selected = allowed_values if value is None else _tuple_value(value, label)
    unknown = set(selected) - set(allowed_values)
    if unknown:
        raise ValueError(f"{label} 包含未声明 ID: " + ", ".join(sorted(unknown)))
    return selected


def _bounded_count(value: Any, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} 必须是整数")
    if not minimum <= value <= maximum:
        raise ValueError(f"{label} 必须在 [{minimum}, {maximum}] 内")
    return value


def _genesis_profile(document: Mapping[str, Any]) -> SpeciesGenesisProfile:
    raw_ranges = document.get("stage_ranges")
    if not isinstance(raw_ranges, Mapping):
        raise ValueError("genesis.stage_ranges 必须是对象")
    stage_ranges: dict[str, tuple[int, int]] = {}
    for stage in _STAGES:
        raw_range = raw_ranges.get(stage)
        if (
            not isinstance(raw_range, (list, tuple))
            or len(raw_range) != 2
            or any(
                isinstance(value, bool) or not isinstance(value, int)
                for value in raw_range
            )
        ):
            raise ValueError(f"genesis.stage_ranges.{stage} 必须是两个整数")
        minimum, maximum = int(raw_range[0]), int(raw_range[1])
        if minimum < 1 or maximum < minimum or maximum > _MAX_AGE_MONTHS:
            raise ValueError(f"genesis.stage_ranges.{stage} 超出安全范围")
        stage_ranges[stage] = (minimum, maximum)
    prior = document.get("personality_prior")
    if (
        not isinstance(prior, (list, tuple))
        or len(prior) != _GENESIS_TRAITS
        or any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            for value in prior
        )
    ):
        raise ValueError("genesis.personality_prior 必须是 5 个数字")
    raw_preferences = document.get("appearance_preferences", {})
    preferences: dict[str, tuple[str, ...]] = {}
    if not isinstance(raw_preferences, Mapping):
        raise ValueError("genesis.appearance_preferences 必须是对象")
    for key, value in raw_preferences.items():
        if not isinstance(key, str):
            raise ValueError("appearance_preferences 的键必须是字符串")
        preferences[key] = _tuple_value(value, f"appearance_preferences.{key}")
    return SpeciesGenesisProfile(
        config_version=_string(document, "config_version"),
        stage_ranges=stage_ranges,
        personality_prior=tuple(float(value) for value in prior),
        appearance_preferences=preferences,
    )


def _read_member(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"缺少物种配置: {path.name}")
    document = read_yaml_mapping(path)
    if document.get("schema_version") != 1:
        raise ValueError(f"{path.name} schema_version 必须是 1")
    return document


def _read_optional_member(path: Path) -> dict[str, Any] | None:
    return None if not path.is_file() else _read_member(path)


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} 必须是对象")
    return value


def _string(mapping: Mapping[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} 必须是非空字符串")
    return value.strip()


def _package_id(mapping: Mapping[str, Any], key: str) -> str:
    value = _string(mapping, key)
    if not _PACKAGE_ID.fullmatch(value):
        raise ValueError(f"{key} 不是合法 package ID")
    return value


def _status(mapping: Mapping[str, Any]) -> SpeciesStatus:
    value = _string(mapping, "status")
    if value not in ("draft", "published", "retired"):
        raise ValueError("status 必须是 draft/published/retired")
    return cast(SpeciesStatus, value)


def _positive_int(mapping: Mapping[str, Any], key: str) -> int:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{key} 必须是正整数")
    return value


def _nonnegative_int(mapping: Mapping[str, Any], key: str) -> int:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} 必须是非负整数")
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} 必须是数字")
    return float(value)


def _scale(mapping: Mapping[str, Any], key: str) -> ScaleRange:
    return _scale_value(_object(mapping.get(key), key), key)


def _scale_value(value: Mapping[str, Any], label: str) -> ScaleRange:
    minimum = _number(value.get("minimum"), f"{label}.minimum")
    base = _number(value.get("base"), f"{label}.base")
    maximum = _number(value.get("maximum"), f"{label}.maximum")
    if not minimum < base < maximum:
        raise ValueError(f"{label} 必须满足 minimum < base < maximum")
    return ScaleRange(minimum, base, maximum)


def _ranges(
    value: Any,
    label: str,
    *,
    optional: bool = False,
) -> Mapping[str, ScaleRange]:
    if value is None and optional:
        return {}
    mapping = _object(value or {}, label)
    return {
        str(key): _scale_value(_object(raw, f"{label}.{key}"), f"{label}.{key}")
        for key, raw in mapping.items()
    }


def _weights(mapping: Mapping[str, Any], key: str) -> CorrelationWeights:
    value = _object(mapping.get(key), key)
    return CorrelationWeights(
        body_fat=_number(value.get("body_fat", 0.0), f"{key}.body_fat"),
        frame_size=_number(value.get("frame_size", 0.0), f"{key}.frame_size"),
        muscularity=_number(value.get("muscularity", 0.0), f"{key}.muscularity"),
        local_bias=_number(value.get("local_bias", 0.0), f"{key}.local_bias"),
    )


def _correlations(value: Any, label: str) -> Mapping[str, CorrelationWeights]:
    if value is None:
        return {}
    mapping = _object(value, label)
    return {str(key): _weights({"value": raw}, "value") for key, raw in mapping.items()}


def _distributions(value: Any) -> Mapping[str, Distribution]:
    if value is None:
        return {}
    mapping = _object(value, "distributions")
    result: dict[str, Distribution] = {}
    for key, raw in mapping.items():
        item = _object(raw, f"distributions.{key}")
        distribution = Distribution(
            mean=_number(item.get("mean", 0.0), f"distributions.{key}.mean"),
            standard_deviation=_number(
                item.get("standard_deviation", 0.34),
                f"distributions.{key}.standard_deviation",
            ),
            minimum=_number(item.get("minimum", -1.0), f"distributions.{key}.minimum"),
            maximum=_number(item.get("maximum", 1.0), f"distributions.{key}.maximum"),
        )
        if (
            distribution.standard_deviation <= 0
            or distribution.minimum > distribution.maximum
        ):
            raise ValueError(f"distributions.{key} 范围无效")
        result[str(key)] = distribution
    return result


def _string_tuple(mapping: Mapping[str, Any], key: str) -> tuple[str, ...]:
    return _tuple_value(mapping.get(key), key)


def _string_tuple_or_default(
    value: Any,
    default: tuple[str, ...],
    label: str,
) -> tuple[str, ...]:
    return default if value is None else _tuple_value(value, label)


def _pattern_color_slots(
    value: Any,
    patterns: tuple[str, ...],
) -> Mapping[str, int]:
    defaults = {
        pattern: {
            "solid": 1,
            "classic": 1,
            "bicolor": 2,
            "tricolor": 3,
            "face_mask": 2,
            "cross": 2,
        }.get(pattern, 1)
        for pattern in patterns
    }
    if value is None:
        return defaults
    mapping = _object(value, "pattern_color_slots")
    result: dict[str, int] = {}
    for pattern in patterns:
        raw = mapping.get(pattern, defaults[pattern])
        if isinstance(raw, bool) or not isinstance(raw, int) or not 1 <= raw <= 4:
            raise ValueError(f"pattern_color_slots.{pattern} 必须是 1 到 4 的整数")
        result[pattern] = raw
    unknown = set(mapping) - set(patterns)
    if unknown:
        raise ValueError(
            "pattern_color_slots 包含未声明的花纹: " + ", ".join(sorted(unknown))
        )
    return result


def _pattern_layouts(
    value: Any,
    patterns: tuple[str, ...],
) -> Mapping[str, tuple[str, ...]]:
    if value is None:
        return {pattern: (pattern,) for pattern in patterns}
    mapping = _object(value, "pattern_layouts")
    result: dict[str, tuple[str, ...]] = {}
    for pattern in patterns:
        raw = mapping.get(pattern, (pattern,))
        layouts = _tuple_value(raw, f"pattern_layouts.{pattern}")
        if len(set(layouts)) != len(layouts):
            raise ValueError(f"pattern_layouts.{pattern} 不得重复")
        result[pattern] = layouts
    unknown = set(mapping) - set(patterns)
    if unknown:
        raise ValueError(
            "pattern_layouts 包含未声明的花纹: " + ", ".join(sorted(unknown))
        )
    return result


def _tuple_value(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError(f"{label} 必须是非空字符串数组")
    result = tuple(
        item.strip() for item in value if isinstance(item, str) and item.strip()
    )
    if len(result) != len(value):
        raise ValueError(f"{label} 必须是非空字符串数组")
    return result


def _string_tuple_maybe_empty(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{label} 必须是字符串数组")
    result = tuple(
        item.strip() for item in value if isinstance(item, str) and item.strip()
    )
    if len(result) != len(value) or len(set(result)) != len(result):
        raise ValueError(f"{label} 必须是无重复字符串数组")
    return result


def _relative_png(mapping: Mapping[str, Any], key: str) -> str:
    value = _string(mapping, key)
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path.suffix.lower() != ".png":
        raise ValueError(f"presentation_images.{key} 必须是包内 PNG")
    return path.as_posix()


def _catalog_digest(root: Path) -> str:
    digest = hashlib.sha256()
    if not root.is_dir():
        raise ValueError("config/species 目录不存在")
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _validate_catalog(catalog: SpeciesCatalog) -> None:
    ids = [item.species_id for item in catalog.definitions]
    if len(ids) != len(set(ids)):
        raise ValueError("物种注册表包含重复的 species_id")
    canon_ids = [item.canon_id for item in catalog.definitions]
    if len(canon_ids) != len(set(canon_ids)):
        raise ValueError("物种注册表包含重复的 canon_id")


__all__ = (
    "BundledSpeciesCatalogSource",
    "SpeciesCatalogError",
    "load_and_configure_species_catalog",
    "load_species_catalog",
    "species_asset_path",
)
