"""Decode the published family-generation policy member."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from elfie.genesis.family_config import (
    FAMILY_GENERATION_VERSION,
    AncestorExpansionConfig,
    ChildrenConfig,
    FamilyGenerationConfig,
    LifespanConfig,
    MarriageAgeConfig,
    PartnerAgeGapConfig,
)


def load_family_generation_config(
    document: Mapping[str, Any],
) -> FamilyGenerationConfig:
    """Decode and validate one complete family-generation YAML document."""

    if document.get("document_kind") != "family_generation_policy":
        raise ValueError("家庭配置 document_kind 无效")
    if document.get("schema_version") != 1:
        raise ValueError("家庭配置 schema_version 无效")
    if document.get("family_generation_version") != FAMILY_GENERATION_VERSION:
        raise ValueError("家庭配置 family_generation_version 无效")
    if document.get("status") != "published":
        raise ValueError("家庭配置必须是 published")

    _ensure_keys(
        document,
        "family",
        required={
            "document_kind",
            "schema_version",
            "family_generation_version",
            "status",
            "marriage",
            "partner_age_gap",
            "children",
            "lifespan",
            "ancestor_expansion",
            "source_ref",
        },
    )

    marriage = _mapping(document, "marriage")
    partner_age_gap = _mapping(document, "partner_age_gap")
    children = _mapping(document, "children")
    lifespan = _mapping(document, "lifespan")
    ancestor_expansion = _mapping(document, "ancestor_expansion")
    _ensure_keys(
        marriage,
        "family.marriage",
        required={"peak_fraction", "stddev_fraction", "never_married_probability"},
    )
    _ensure_keys(
        partner_age_gap,
        "family.partner_age_gap",
        required={"offsets", "weights"},
    )
    _ensure_keys(
        children,
        "family.children",
        required={
            "count_distribution",
            "max_count",
            "birth_lag_decay",
            "sex_distribution",
        },
    )
    _ensure_keys(
        lifespan,
        "family.lifespan",
        required={"early_cdf_power", "late_survival_power"},
    )
    _ensure_keys(
        ancestor_expansion,
        "family.ancestor_expansion",
        required={"max_upward_generations", "stop_at_elder"},
    )

    count_distribution = _number_mapping(
        _mapping(children, "count_distribution"),
        "family.children.count_distribution",
    )
    sex_distribution = _number_mapping(
        _mapping(children, "sex_distribution"),
        "family.children.sex_distribution",
    )
    config = FamilyGenerationConfig(
        generation_version=_text(document, "family_generation_version"),
        marriage=MarriageAgeConfig(
            peak_fraction=_number(marriage, "peak_fraction"),
            stddev_fraction=_number(marriage, "stddev_fraction"),
            never_married_probability=_number(marriage, "never_married_probability"),
        ),
        partner_age_gap=PartnerAgeGapConfig(
            offsets=_integers(partner_age_gap, "offsets"),
            weights=_numbers(partner_age_gap, "weights"),
        ),
        children=ChildrenConfig(
            count_distribution=tuple(
                (int(count), weight) for count, weight in count_distribution
            ),
            max_count=_integer(children, "max_count"),
            birth_lag_decay=_number(children, "birth_lag_decay"),
            sex_distribution=tuple(sex_distribution),
        ),
        lifespan=LifespanConfig(
            early_cdf_power=_integer(lifespan, "early_cdf_power"),
            late_survival_power=_integer(lifespan, "late_survival_power"),
        ),
        ancestor_expansion=AncestorExpansionConfig(
            max_upward_generations=_integer(
                ancestor_expansion, "max_upward_generations"
            ),
            stop_at_elder=_boolean(ancestor_expansion, "stop_at_elder"),
        ),
    )
    config.validate()
    return config


def _ensure_keys(value: Mapping[str, Any], label: str, *, required: set[str]) -> None:
    missing = required - set(value)
    if missing:
        raise ValueError(f"{label} 缺少字段: {', '.join(sorted(missing))}")
    unknown = set(value) - required
    if unknown:
        raise ValueError(f"{label} 含有未知字段: {', '.join(sorted(unknown))}")


def _mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    nested = value.get(key)
    if not isinstance(nested, Mapping):
        raise ValueError(f"家庭配置缺少对象: {key}")
    return nested


def _text(value: Mapping[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise ValueError(f"家庭配置 {key} 必须是非空字符串")
    return result


def _number(value: Mapping[str, Any], key: str) -> float:
    result = value.get(key)
    if isinstance(result, bool) or not isinstance(result, (int, float)):
        raise ValueError(f"家庭配置 {key} 必须是数字")
    number = float(result)
    if not math.isfinite(number):
        raise ValueError(f"家庭配置 {key} 必须是有限数字")
    return number


def _integer(value: Mapping[str, Any], key: str) -> int:
    result = value.get(key)
    if isinstance(result, bool) or not isinstance(result, int):
        raise ValueError(f"家庭配置 {key} 必须是整数")
    return result


def _boolean(value: Mapping[str, Any], key: str) -> bool:
    result = value.get(key)
    if not isinstance(result, bool):
        raise ValueError(f"家庭配置 {key} 必须是布尔值")
    return result


def _integers(value: Mapping[str, Any], key: str) -> tuple[int, ...]:
    result = value.get(key)
    if not isinstance(result, (list, tuple)):
        raise ValueError(f"家庭配置 {key} 必须是整数数组")
    if any(isinstance(item, bool) or not isinstance(item, int) for item in result):
        raise ValueError(f"家庭配置 {key} 必须是整数数组")
    return tuple(result)


def _numbers(value: Mapping[str, Any], key: str) -> tuple[float, ...]:
    result = value.get(key)
    if not isinstance(result, (list, tuple)):
        raise ValueError(f"家庭配置 {key} 必须是数字数组")
    numbers = tuple(float(item) for item in result)
    if any(not math.isfinite(item) for item in numbers):
        raise ValueError(f"家庭配置 {key} 必须是有限数字数组")
    return numbers


def _number_mapping(
    value: Mapping[str, Any], label: str
) -> tuple[tuple[str, float], ...]:
    return tuple((str(key), _number(value, str(key))) for key in value)
