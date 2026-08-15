"""Curated, optional cross-Provider model identity matching."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from infrastructure.persistence.configuration.documents import (
    BundledConfigSource,
    ConfigDocumentId,
)

MODEL_CATALOG_VERSION = 1
_SEPARATORS = re.compile(r"[\s_]+")
_CATALOG_FIELDS = frozenset({"version", "models", "entries"})
_IDENTITY_FIELDS = frozenset(
    {
        "display_name",
        "aliases",
        "context_window_tokens",
        "max_output_tokens",
        "supports_tools",
        "supports_vision",
        "supports_reasoning",
        "supports_structured_output",
    }
)


class ModelIdentityCatalogError(RuntimeError):
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
    supports_structured_output: Optional[bool] = None


@dataclass(frozen=True)
class EndpointModelDeclaration:
    """Static metadata declared for one exact Provider/model endpoint."""

    provider_id: str
    endpoint_model_id: str
    display_name: str
    context_window_tokens: Optional[int] = None
    max_output_tokens: Optional[int] = None
    supports_tools: Optional[bool] = None
    supports_vision: Optional[bool] = None
    supports_reasoning: Optional[bool] = None
    supports_structured_output: Optional[bool] = None


@dataclass(frozen=True)
class ModelIdentityCatalog:
    """Validated model identities and their normalized alias index."""

    identities: Mapping[str, CanonicalModelIdentity]
    aliases: Mapping[str, CanonicalModelIdentity]
    endpoint_declarations: Mapping[str, EndpointModelDeclaration] = field(
        default_factory=dict
    )

    def match(
        self,
        endpoint_model_id: str,
        display_name: str = "",
    ) -> Optional[CanonicalModelIdentity]:
        for candidate in (endpoint_model_id, display_name):
            normalized = _normalize(candidate)
            if normalized and normalized in self.aliases:
                return self.aliases[normalized]
        return None

    def endpoint_declaration(
        self, provider_id: str, endpoint_model_id: str
    ) -> Optional[EndpointModelDeclaration]:
        return self.endpoint_declarations.get(
            f"{provider_id.strip()}/{endpoint_model_id.strip()}"
        )


def load_model_identities(
    root: Path | None = None,
) -> ModelIdentityCatalog:
    loaded = BundledConfigSource(root).load(ConfigDocumentId.MODEL_CATALOG)
    return parse_model_identities(loaded.document, loaded.path)


def parse_model_identities(
    document: Mapping[str, Any],
    source: Path,
) -> ModelIdentityCatalog:
    if not isinstance(document, Mapping):
        raise ModelIdentityCatalogError(f"标准模型目录顶层必须是对象: {source}")
    if document.get("version") != MODEL_CATALOG_VERSION:
        raise ModelIdentityCatalogError(f"不支持的标准模型目录版本: {source}")
    _reject_unknown(document, _CATALOG_FIELDS, "标准模型目录", source)
    raw_models = document.get("models")
    if not isinstance(raw_models, Mapping):
        raise ModelIdentityCatalogError(f"标准模型目录缺少 models: {source}")
    identities: Dict[str, CanonicalModelIdentity] = {}
    for canonical_id, raw in raw_models.items():
        if not isinstance(canonical_id, str) or not isinstance(raw, Mapping):
            raise ModelIdentityCatalogError(f"标准模型记录不合法: {source}")
        _reject_unknown(raw, _IDENTITY_FIELDS, f"标准模型 {canonical_id!r}", source)
        display_name = raw.get("display_name")
        raw_aliases = raw.get("aliases", [])
        if (
            not isinstance(display_name, str)
            or not display_name.strip()
            or not isinstance(raw_aliases, list)
        ):
            raise ModelIdentityCatalogError(
                f"标准模型 {canonical_id!r} 缺少名称或别名: {source}"
            )
        if any(
            not isinstance(alias, str) or not alias.strip() for alias in raw_aliases
        ):
            raise ModelIdentityCatalogError(
                f"标准模型 {canonical_id!r} 的别名必须是字符串: {source}"
            )
        aliases = tuple(
            dict.fromkeys(
                alias.strip() for alias in [display_name, *raw_aliases] if alias.strip()
            )
        )
        identities[canonical_id] = CanonicalModelIdentity(
            canonical_model_id=canonical_id,
            display_name=display_name.strip(),
            aliases=aliases,
            context_window_tokens=_optional_positive_int(
                raw.get("context_window_tokens")
            ),
            max_output_tokens=_optional_positive_int(raw.get("max_output_tokens")),
            supports_tools=_optional_bool(raw.get("supports_tools")),
            supports_vision=_optional_bool(raw.get("supports_vision")),
            supports_reasoning=_optional_bool(raw.get("supports_reasoning")),
            supports_structured_output=_optional_bool(
                raw.get("supports_structured_output")
            ),
        )
    alias_index = {
        _normalize(alias): identity
        for identity in identities.values()
        for alias in identity.aliases
    }
    endpoint_declarations: Dict[str, EndpointModelDeclaration] = {}
    raw_entries = document.get("entries", {})
    if not isinstance(raw_entries, Mapping):
        raise ModelIdentityCatalogError(f"标准模型目录 entries 必须是对象: {source}")
    for entry_id, raw in raw_entries.items():
        if not isinstance(entry_id, str) or not isinstance(raw, Mapping):
            raise ModelIdentityCatalogError(f"标准模型 Endpoint 记录不合法: {source}")
        provider_id = raw.get("provider")
        display_name = raw.get("display_name")
        capabilities = raw.get("capabilities", [])
        if (
            not isinstance(provider_id, str)
            or not provider_id.strip()
            or not isinstance(display_name, str)
            or not display_name.strip()
            or not isinstance(capabilities, list)
            or any(not isinstance(item, str) for item in capabilities)
        ):
            raise ModelIdentityCatalogError(
                f"标准模型 Endpoint {entry_id!r} 缺少合法 provider/display_name/capabilities: {source}"
            )
        if "/" not in entry_id:
            raise ModelIdentityCatalogError(
                f"标准模型 Endpoint 标识必须为 provider/model: {source}"
            )
        declared_provider, endpoint_model_id = entry_id.split("/", 1)
        if declared_provider != provider_id.strip() or not endpoint_model_id.strip():
            raise ModelIdentityCatalogError(
                f"标准模型 Endpoint provider 与标识不一致: {source}"
            )
        capability_set = {item.strip().lower() for item in capabilities}
        endpoint_declarations[entry_id] = EndpointModelDeclaration(
            provider_id=provider_id.strip(),
            endpoint_model_id=endpoint_model_id.strip(),
            display_name=display_name.strip(),
            context_window_tokens=_optional_positive_int(raw.get("context_window")),
            max_output_tokens=_optional_positive_int(
                raw.get("max_output_tokens", raw.get("max_output"))
            ),
            supports_tools=(True if "tools" in capability_set else None),
            supports_vision=(True if "vision" in capability_set else None),
            supports_reasoning=(True if "reasoning" in capability_set else None),
            supports_structured_output=(
                True if "structured_output" in capability_set else None
            ),
        )
    return ModelIdentityCatalog(
        identities=identities,
        aliases=alias_index,
        endpoint_declarations=endpoint_declarations,
    )


def match_model_identity(
    endpoint_model_id: str,
    display_name: str = "",
    *,
    catalog: ModelIdentityCatalog | None = None,
) -> Optional[CanonicalModelIdentity]:
    """Match only exact curated aliases after harmless separator normalization."""
    return (catalog or load_model_identities()).match(endpoint_model_id, display_name)


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


def _reject_unknown(
    raw: Mapping[str, Any],
    allowed: frozenset[str],
    label: str,
    source: Path,
) -> None:
    unknown = sorted(str(key) for key in set(raw) - allowed)
    if unknown:
        raise ModelIdentityCatalogError(f"{label} 包含未知字段 {unknown}: {source}")


__all__ = (
    "CanonicalModelIdentity",
    "EndpointModelDeclaration",
    "ModelIdentityCatalog",
    "ModelIdentityCatalogError",
    "load_model_identities",
    "match_model_identity",
    "parse_model_identities",
)
