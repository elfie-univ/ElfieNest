"""Typed-family entry points for bundled default documents."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from infrastructure.persistence.configuration.documents import (
    BundledConfigSource,
    ConfigDocumentError,
    ConfigDocumentId,
)
from nest.public import NestConfig, NestConfigError


def load_bundled_document(
    document_id: ConfigDocumentId,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Load one registered bundled document as an isolated mapping."""

    return deepcopy(dict(BundledConfigSource(root).load(document_id).document))


def load_system_defaults(*, root: Path | None = None) -> dict[str, Any]:
    document = load_bundled_document(ConfigDocumentId.SYSTEM_DEFAULTS, root=root)
    value = document.get("system")
    if not isinstance(value, Mapping):
        raise ConfigDocumentError("system-defaults.yaml 缺少 system 对象")
    return deepcopy(dict(value))


def load_tool_defaults(*, root: Path | None = None) -> dict[str, dict[str, Any]]:
    document = load_bundled_document(ConfigDocumentId.TOOL_DEFAULTS, root=root)
    value = document.get("tools")
    if not isinstance(value, Mapping):
        raise ConfigDocumentError("tools/defaults.yaml 缺少 tools 对象")
    result: dict[str, dict[str, Any]] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or not isinstance(raw, Mapping):
            raise ConfigDocumentError("tools/defaults.yaml 的工具记录必须是对象")
        result[key] = deepcopy(dict(raw))
    return result


def _load_brain_section(
    document_id: ConfigDocumentId,
    *,
    root: Path | None,
) -> dict[str, Any]:
    document = load_bundled_document(document_id, root=root)
    document.pop("version", None)
    return document


def load_energy_defaults(*, root: Path | None = None) -> dict[str, Any]:
    return _load_brain_section(ConfigDocumentId.ENERGY_DEFAULTS, root=root)


def load_selfhood_defaults(*, root: Path | None = None) -> dict[str, Any]:
    return _load_brain_section(ConfigDocumentId.SELFHOOD_DEFAULTS, root=root)


def load_reasoning_constitution(*, root: Path | None = None) -> dict[str, Any]:
    """Load the required release-owned online Reasoning constitution."""

    # Unlike tunable Brain defaults, the Constitution's document version is a
    # captured source revision and must reach ``ReasoningConstitution``.
    return load_bundled_document(ConfigDocumentId.REASONING_CONSTITUTION, root=root)


def load_emotion_expression_defaults(*, root: Path | None = None) -> dict[str, Any]:
    return _load_brain_section(ConfigDocumentId.EMOTION_EXPRESSIONS, root=root)


def load_emotion_dynamics_defaults(*, root: Path | None = None) -> dict[str, Any]:
    return _load_brain_section(ConfigDocumentId.EMOTION_DYNAMICS, root=root)


def load_nest_config(*, root: Path | None = None) -> NestConfig:
    """Load the typed Nest initialization defaults from the bundled root."""

    document = load_bundled_document(ConfigDocumentId.NEST_DEFAULTS, root=root)
    value = document.get("nest")
    if not isinstance(value, Mapping):
        raise ConfigDocumentError("nest/defaults.yaml 缺少 nest 对象")
    raw_bed_count = value.get("bed_count")
    if isinstance(raw_bed_count, bool) or not isinstance(raw_bed_count, int):
        raise ConfigDocumentError("nest/defaults.yaml 的 bed_count 必须是整数")
    try:
        return NestConfig(bed_count=raw_bed_count)
    except (NestConfigError, TypeError, ValueError) as error:
        raise ConfigDocumentError("nest/defaults.yaml 的 Nest 配置无效") from error


__all__ = (
    "load_bundled_document",
    "load_emotion_expression_defaults",
    "load_emotion_dynamics_defaults",
    "load_energy_defaults",
    "load_nest_config",
    "load_selfhood_defaults",
    "load_reasoning_constitution",
    "load_system_defaults",
    "load_tool_defaults",
)
