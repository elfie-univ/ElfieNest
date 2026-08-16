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
    SPECIES_CANON_VERSION,
    CorrelationWeights,
    Distribution,
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
    profile = SpeciesAppearanceProfile(
        species_id=species_id,
        profile_version=_positive_int(document, "profile_version"),
        stature_scale=_scale(document, "stature_scale"),
        build_scale=_scale(document, "build_scale"),
        build_weights=_weights(document, "build_weights"),
        palettes=_string_tuple(document, "palettes"),
        patterns=_string_tuple(document, "patterns"),
        eye_colors=_string_tuple(document, "eye_colors"),
        nose_colors=_string_tuple(document, "nose_colors"),
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


def _tuple_value(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError(f"{label} 必须是非空字符串数组")
    result = tuple(
        item.strip() for item in value if isinstance(item, str) and item.strip()
    )
    if len(result) != len(value):
        raise ValueError(f"{label} 必须是非空字符串数组")
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
