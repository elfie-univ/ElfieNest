"""Typed records for Provider connection configuration version 2."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Mapping, Optional, Tuple, cast

CONNECTION_DOCUMENT_VERSION = 2
_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
CONNECTION_ID_PATTERN = re.compile(r"^([a-z][a-z0-9_]{0,54})_(\d{4,})$")
ModelSource = Literal[
    "official",
    "remote_catalog",
    "bundled_catalog",
    "manual",
]
ModelPricing = Literal["free", "unknown"]
DiscoveryState = Literal["present", "source_missing"]
CapabilityEvidenceLevel = Literal[
    "declared",
    "declared_by_user",
    "accepted",
    "verified",
    "unknown",
]
_MODEL_SOURCES = frozenset({"official", "remote_catalog", "bundled_catalog", "manual"})
_DISCOVERY_STATES = frozenset({"present", "source_missing"})
_CAPABILITY_NAMES = frozenset({"tools", "vision", "reasoning", "structured_output"})
_CAPABILITY_EVIDENCE = frozenset(
    {"declared", "declared_by_user", "accepted", "verified", "unknown"}
)
_DOCUMENT_FIELDS = frozenset({"version", "connection_counters", "connections"})
_CONNECTION_FIELDS = frozenset(
    {
        "catalog_id",
        "alias",
        "api_base",
        "api_mode",
        "auth_type",
        "credential_ref",
        "installation",
        "models",
        "enabled",
        "archived",
    }
)
_MODEL_FIELDS = frozenset(
    {
        "id",
        "display_name",
        "source",
        "request_profile_id",
        "request_profile_version",
        "canonical_model_id",
        "context_window_tokens",
        "max_output_tokens",
        "supports_tools",
        "supports_vision",
        "supports_reasoning",
        "supports_structured_output",
        "capability_evidence",
        "hidden",
        "retired",
        "available",
        "discovery_state",
        "consecutive_missing",
        "last_seen_at",
        "pricing",
    }
)


class InvalidProviderConnectionDocument(ValueError):
    """The v2 Provider connection document is malformed."""


def is_connection_id(value: str) -> bool:
    return CONNECTION_ID_PATTERN.fullmatch(value) is not None


@dataclass(frozen=True)
class ProviderModelRecord:
    """One endpoint-specific model exposed by a connection."""

    endpoint_model_id: str
    display_name: str = ""
    canonical_model_id: Optional[str] = None
    source: ModelSource = "manual"
    request_profile_id: Optional[str] = None
    request_profile_version: Optional[int] = None
    context_window_tokens: Optional[int] = None
    max_output_tokens: Optional[int] = None
    supports_tools: Optional[bool] = None
    supports_vision: Optional[bool] = None
    supports_reasoning: Optional[bool] = None
    supports_structured_output: Optional[bool] = None
    capability_evidence: Mapping[str, CapabilityEvidenceLevel] = field(
        default_factory=dict
    )
    hidden: bool = False
    retired: bool = False
    available: bool = True
    discovery_state: DiscoveryState = "present"
    consecutive_missing: int = 0
    last_seen_at: Optional[str] = None
    pricing: ModelPricing = "unknown"

    def __post_init__(self) -> None:
        endpoint_model_id = self.endpoint_model_id.strip()
        if not endpoint_model_id:
            raise ValueError("endpoint_model_id 不能为空")
        if self.source not in _MODEL_SOURCES:
            raise ValueError(f"未知模型来源: {self.source}")
        if self.discovery_state not in _DISCOVERY_STATES:
            raise ValueError(f"未知模型发现状态: {self.discovery_state}")
        if self.pricing not in {"free", "unknown"}:
            raise ValueError(f"未知模型计价方式: {self.pricing}")
        if self.request_profile_id is None and self.request_profile_version is not None:
            raise ValueError("request_profile_version 不能脱离 request_profile_id")
        if (
            self.request_profile_version is not None
            and self.request_profile_version <= 0
        ):
            raise ValueError("request_profile_version 必须为正整数")
        evidence = dict(self.capability_evidence)
        if set(evidence) - _CAPABILITY_NAMES:
            raise ValueError("capability_evidence 包含未知能力")
        if any(
            not isinstance(value, str) or value not in _CAPABILITY_EVIDENCE
            for value in evidence.values()
        ):
            raise ValueError("capability_evidence 包含未知证据等级")
        if isinstance(self.consecutive_missing, bool) or self.consecutive_missing < 0:
            raise ValueError("consecutive_missing 不能为负数")
        for value, name in (
            (self.context_window_tokens, "context_window_tokens"),
            (self.max_output_tokens, "max_output_tokens"),
        ):
            if value is not None and value <= 0:
                raise ValueError(f"{name} 必须为正整数")
        object.__setattr__(self, "endpoint_model_id", endpoint_model_id)
        object.__setattr__(
            self, "display_name", self.display_name.strip() or endpoint_model_id
        )
        if self.canonical_model_id is not None:
            canonical = self.canonical_model_id.strip()
            object.__setattr__(self, "canonical_model_id", canonical or None)
        if self.request_profile_id is not None:
            profile_id = self.request_profile_id.strip()
            object.__setattr__(self, "request_profile_id", profile_id or None)
        if self.request_profile_id is None and self.request_profile_version is not None:
            raise ValueError("request_profile_version 不能脱离 request_profile_id")
        if self.request_profile_id:
            from infrastructure.models.providers.request_profiles import (
                get_request_profile,
            )

            try:
                get_request_profile(
                    self.request_profile_id,
                    self.request_profile_version,
                )
            except ValueError as error:
                raise ValueError("request_profile_id 或版本无效") from error
        object.__setattr__(self, "capability_evidence", evidence)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.endpoint_model_id,
            "display_name": self.display_name,
            "source": self.source,
        }
        if self.request_profile_id:
            result["request_profile_id"] = self.request_profile_id
        if self.request_profile_version is not None:
            result["request_profile_version"] = self.request_profile_version
        optional = {
            "canonical_model_id": self.canonical_model_id,
            "context_window_tokens": self.context_window_tokens,
            "max_output_tokens": self.max_output_tokens,
            "supports_tools": self.supports_tools,
            "supports_vision": self.supports_vision,
            "supports_reasoning": self.supports_reasoning,
            "supports_structured_output": self.supports_structured_output,
            "capability_evidence": (
                dict(self.capability_evidence) if self.capability_evidence else None
            ),
        }
        result.update(
            {key: value for key, value in optional.items() if value is not None}
        )
        if self.hidden:
            result["hidden"] = True
        if self.retired:
            result["retired"] = True
        # ``available`` remains readable for old v2 documents, but current
        # availability is evidence-derived and must never be persisted here.
        if self.discovery_state != "present":
            result["discovery_state"] = self.discovery_state
        if self.consecutive_missing:
            result["consecutive_missing"] = self.consecutive_missing
        if self.last_seen_at:
            result["last_seen_at"] = self.last_seen_at
        if self.pricing == "free":
            result["pricing"] = self.pricing
        return result

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> ProviderModelRecord:
        _reject_unknown(raw, _MODEL_FIELDS, "模型配置")
        raw_source = str(raw.get("source") or "manual")
        if raw_source not in _MODEL_SOURCES:
            raise ValueError(f"未知模型来源: {raw_source}")
        return cls(
            endpoint_model_id=str(raw.get("id") or ""),
            display_name=str(raw.get("display_name") or ""),
            canonical_model_id=_optional_string(raw.get("canonical_model_id")),
            source=cast(ModelSource, raw_source),
            request_profile_id=_optional_string(raw.get("request_profile_id")),
            request_profile_version=_optional_positive_int(
                raw.get("request_profile_version"), "request_profile_version"
            ),
            context_window_tokens=_optional_positive_int(
                raw.get("context_window_tokens"), "context_window_tokens"
            ),
            max_output_tokens=_optional_positive_int(
                raw.get("max_output_tokens"), "max_output_tokens"
            ),
            supports_tools=_optional_bool(raw.get("supports_tools"), "supports_tools"),
            supports_vision=_optional_bool(
                raw.get("supports_vision"), "supports_vision"
            ),
            supports_reasoning=_optional_bool(
                raw.get("supports_reasoning"), "supports_reasoning"
            ),
            supports_structured_output=_optional_bool(
                raw.get("supports_structured_output"),
                "supports_structured_output",
            ),
            capability_evidence=_capability_evidence(
                raw.get("capability_evidence", {})
            ),
            hidden=_required_bool(raw.get("hidden", False), "hidden"),
            retired=_required_bool(raw.get("retired", False), "retired"),
            available=_required_bool(raw.get("available", True), "available"),
            discovery_state=_discovery_state(raw.get("discovery_state", "present")),
            consecutive_missing=_optional_non_negative_int(
                raw.get("consecutive_missing", 0), "consecutive_missing"
            ),
            last_seen_at=_optional_string(raw.get("last_seen_at")),
            pricing=_pricing(raw.get("pricing", "unknown")),
        )


@dataclass(frozen=True)
class ProviderConnection:
    """One configured account, subscription, or local model endpoint."""

    connection_id: str
    catalog_id: str
    alias: str
    api_base: str = ""
    api_mode: str = ""
    auth_type: str = ""
    credential_ref: str = ""
    installation: Mapping[str, str] = field(default_factory=dict)
    models: Tuple[ProviderModelRecord, ...] = ()
    enabled: bool = True
    archived: bool = False

    def __post_init__(self) -> None:
        if CONNECTION_ID_PATTERN.fullmatch(self.connection_id) is None:
            raise ValueError(f"无效 connection_id: {self.connection_id!r}")
        if _ID_PATTERN.fullmatch(self.catalog_id) is None:
            raise ValueError(f"无效 catalog_id: {self.catalog_id!r}")
        alias = self.alias.strip()
        if not alias:
            raise ValueError("alias 不能为空")
        model_ids = [model.endpoint_model_id for model in self.models]
        if len(set(model_ids)) != len(model_ids):
            raise ValueError("连接中的模型 ID 不能重复")
        if self.archived and self.enabled:
            raise ValueError("归档连接不能启用")
        object.__setattr__(self, "alias", alias)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "catalog_id": self.catalog_id,
            "alias": self.alias,
            "enabled": self.enabled,
            "archived": self.archived,
        }
        optional = {
            "api_base": self.api_base,
            "api_mode": self.api_mode,
            "auth_type": self.auth_type,
            "credential_ref": self.credential_ref,
        }
        result.update({key: value for key, value in optional.items() if value})
        if self.installation:
            result["installation"] = dict(self.installation)
        result["models"] = [model.to_dict() for model in self.models]
        return result

    @classmethod
    def from_dict(
        cls, connection_id: str, raw: Mapping[str, Any]
    ) -> ProviderConnection:
        _reject_unknown(raw, _CONNECTION_FIELDS, "连接配置")
        raw_models = raw.get("models", [])
        raw_installation = raw.get("installation", {})
        if not isinstance(raw_models, list):
            raise ValueError("models 必须是数组")
        if not isinstance(raw_installation, Mapping):
            raise ValueError("installation 必须是对象")
        if any(not isinstance(model, Mapping) for model in raw_models):
            raise ValueError("模型配置必须是对象")
        return cls(
            connection_id=connection_id,
            catalog_id=str(raw.get("catalog_id") or ""),
            alias=str(raw.get("alias") or ""),
            api_base=str(raw.get("api_base") or ""),
            api_mode=str(raw.get("api_mode") or ""),
            auth_type=str(raw.get("auth_type") or ""),
            credential_ref=str(raw.get("credential_ref") or ""),
            installation={
                str(key): str(value)
                for key, value in raw_installation.items()
                if value is not None
            },
            models=tuple(ProviderModelRecord.from_dict(model) for model in raw_models),
            enabled=_required_bool(raw.get("enabled", True), "enabled"),
            archived=_required_bool(raw.get("archived", False), "archived"),
        )


@dataclass(frozen=True)
class ProviderConnectionDocument:
    version: int = CONNECTION_DOCUMENT_VERSION
    counters: Dict[str, int] = field(default_factory=dict)
    connections: Dict[str, ProviderConnection] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": CONNECTION_DOCUMENT_VERSION,
            "connection_counters": dict(sorted(self.counters.items())),
            "connections": {
                key: value.to_dict() for key, value in self.connections.items()
            },
        }


def parse_provider_document(raw: Mapping[str, Any]) -> ProviderConnectionDocument:
    version = raw.get("version")
    if version != CONNECTION_DOCUMENT_VERSION:
        raise InvalidProviderConnectionDocument(
            f"只支持 Provider 连接配置 v2，收到版本: {version!r}"
        )
    _reject_unknown(raw, _DOCUMENT_FIELDS, "Provider 连接文档")
    raw_counters = raw.get("connection_counters", {})
    raw_connections = raw.get("connections", {})
    if not isinstance(raw_counters, Mapping) or not isinstance(
        raw_connections, Mapping
    ):
        raise InvalidProviderConnectionDocument(
            "connection_counters 和 connections 必须是对象"
        )
    counters: Dict[str, int] = {}
    for catalog_id, value in raw_counters.items():
        if not isinstance(catalog_id, str) or _ID_PATTERN.fullmatch(catalog_id) is None:
            raise InvalidProviderConnectionDocument(f"无效 catalog_id: {catalog_id!r}")
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise InvalidProviderConnectionDocument(f"无效连接序号: {catalog_id}")
        counters[catalog_id] = value
    connections: Dict[str, ProviderConnection] = {}
    try:
        for connection_id, value in raw_connections.items():
            if not isinstance(connection_id, str) or not isinstance(value, Mapping):
                raise ValueError("连接配置必须是对象")
            connections[connection_id] = ProviderConnection.from_dict(
                connection_id, value
            )
    except ValueError as exc:
        raise InvalidProviderConnectionDocument(str(exc)) from exc
    return ProviderConnectionDocument(counters=counters, connections=connections)


def _optional_string(value: Any) -> Optional[str]:
    normalized = str(value or "").strip()
    return normalized or None


def _pricing(value: Any) -> ModelPricing:
    if value not in {"free", "unknown"}:
        raise ValueError(f"未知模型计价方式: {value}")
    return cast(ModelPricing, value)


def _optional_positive_int(value: Any, field_name: str) -> Optional[int]:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field_name} 必须为正整数")
    return value


def _optional_non_negative_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} 必须是非负整数")
    return value


def _discovery_state(value: Any) -> DiscoveryState:
    if value not in _DISCOVERY_STATES:
        raise ValueError(f"未知模型发现状态: {value}")
    return cast(DiscoveryState, value)


def _optional_bool(value: Any, field_name: str) -> Optional[bool]:
    if value is None:
        return None
    return _required_bool(value, field_name)


def _capability_evidence(value: Any) -> dict[str, CapabilityEvidenceLevel]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("capability_evidence 必须是对象")
    result: dict[str, CapabilityEvidenceLevel] = {}
    for name, evidence in value.items():
        if not isinstance(name, str) or name not in _CAPABILITY_NAMES:
            raise ValueError(f"未知能力: {name}")
        if not isinstance(evidence, str) or evidence not in _CAPABILITY_EVIDENCE:
            raise ValueError(f"未知能力证据等级: {evidence}")
        result[str(name)] = cast(CapabilityEvidenceLevel, evidence)
    return result


def _required_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} 必须为布尔值")
    return value


def _reject_unknown(
    raw: Mapping[str, Any],
    allowed: frozenset[str],
    label: str,
) -> None:
    unknown = sorted(str(key) for key in set(raw) - allowed)
    if unknown:
        raise ValueError(f"{label}包含未知字段: {unknown}")
