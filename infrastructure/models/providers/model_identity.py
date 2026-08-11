"""Curated, optional cross-Provider model identity matching."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from infrastructure.persistence.configuration.config_store import (
    ConfigStoreError,
    read_yaml_mapping,
)

MODEL_CATALOG_VERSION = 1
BUNDLED_MODEL_CATALOG_PATH = Path(__file__).with_name("model-catalog.yaml")
_SEPARATORS = re.compile(r"[\s_]+")


class ModelIdentityCatalogError(ConfigStoreError):
    """The curated model identity catalog is malformed."""


@dataclass(frozen=True)
class CanonicalModelIdentity:
    canonical_model_id: str
    display_name: str
    aliases: Tuple[str, ...]
    context_window_tokens: Optional[int] = None
    max_output_tokens: Optional[int] = None
    supports_tools: Optional[bool] = None
    supports_vision: Optional[bool] = None
    supports_reasoning: Optional[bool] = None


def load_model_identities(
    path: Path = BUNDLED_MODEL_CATALOG_PATH,
) -> Dict[str, CanonicalModelIdentity]:
    document = read_yaml_mapping(path)
    if document.get("version") != MODEL_CATALOG_VERSION:
        raise ModelIdentityCatalogError("不支持的标准模型目录版本")
    raw_models = document.get("models")
    if not isinstance(raw_models, Mapping):
        raise ModelIdentityCatalogError("标准模型目录缺少 models")
    identities: Dict[str, CanonicalModelIdentity] = {}
    for canonical_id, raw in raw_models.items():
        if not isinstance(canonical_id, str) or not isinstance(raw, Mapping):
            raise ModelIdentityCatalogError("标准模型记录不合法")
        display_name = str(raw.get("display_name") or "").strip()
        raw_aliases = raw.get("aliases", [])
        if not display_name or not isinstance(raw_aliases, list):
            raise ModelIdentityCatalogError(f"标准模型 {canonical_id!r} 缺少名称或别名")
        aliases = tuple(
            dict.fromkeys(
                str(alias).strip()
                for alias in [display_name, *raw_aliases]
                if str(alias).strip()
            )
        )
        identities[canonical_id] = CanonicalModelIdentity(
            canonical_model_id=canonical_id,
            display_name=display_name,
            aliases=aliases,
            context_window_tokens=_optional_positive_int(
                raw.get("context_window_tokens")
            ),
            max_output_tokens=_optional_positive_int(raw.get("max_output_tokens")),
            supports_tools=_optional_bool(raw.get("supports_tools")),
            supports_vision=_optional_bool(raw.get("supports_vision")),
            supports_reasoning=_optional_bool(raw.get("supports_reasoning")),
        )
    return identities


def match_model_identity(
    endpoint_model_id: str,
    display_name: str = "",
) -> Optional[CanonicalModelIdentity]:
    """Match only exact curated aliases after harmless separator normalization."""
    for candidate in (endpoint_model_id, display_name):
        normalized = _normalize(candidate)
        if normalized and normalized in _ALIAS_INDEX:
            return _ALIAS_INDEX[normalized]
    return None


def _normalize(value: str) -> str:
    return _SEPARATORS.sub("-", value.strip().lower())


def _optional_positive_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ModelIdentityCatalogError("模型 token 限制必须为正整数")
    return value


def _optional_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ModelIdentityCatalogError("模型能力字段必须为布尔值")
    return value


MODEL_IDENTITIES = load_model_identities()
_ALIAS_INDEX = {
    _normalize(alias): identity
    for identity in MODEL_IDENTITIES.values()
    for alias in identity.aliases
}
