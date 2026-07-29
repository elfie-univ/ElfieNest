"""Versioned Provider connection instance storage."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Literal, Mapping, Optional, Tuple

from ai_runtime.storage.config_store import (
    ConfigStoreError,
    read_yaml_mapping,
    write_yaml_mapping,
)
from ai_runtime.storage.data_home import (
    ensure_elfie_home,
    get_provider_config_path,
)

CONNECTION_DOCUMENT_VERSION = 2
_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_CONNECTION_ID_PATTERN = re.compile(r"^([a-z][a-z0-9_]{0,54})_(\d{4,})$")
_MODEL_SOURCES = frozenset({"discovered", "manual", "provider_catalog"})
_LEGACY_CATALOG_IDS = {
    "ollama": "ollama",
    "openai": "openai_api",
    "anthropic": "anthropic_api",
    "deepseek": "deepseek_api",
    "gemini": "gemini_api",
    "qwen": "qwen_api",
    "xai": "xai_api",
    "mistral": "mistral_api",
    "groq": "groq_api",
    "custom_openai": "custom_openai",
}


class ProviderConnectionStoreError(ConfigStoreError):
    """Provider connection configuration is malformed."""


def is_connection_id(value: str) -> bool:
    return _CONNECTION_ID_PATTERN.fullmatch(value) is not None


@dataclass(frozen=True)
class ProviderModelRecord:
    """One endpoint-specific model exposed by a connection."""

    endpoint_model_id: str
    display_name: str = ""
    canonical_model_id: Optional[str] = None
    source: Literal["discovered", "manual", "provider_catalog"] = "manual"
    context_window_tokens: Optional[int] = None
    max_output_tokens: Optional[int] = None
    supports_tools: Optional[bool] = None
    supports_vision: Optional[bool] = None
    supports_reasoning: Optional[bool] = None
    hidden: bool = False

    def __post_init__(self) -> None:
        endpoint_model_id = self.endpoint_model_id.strip()
        if not endpoint_model_id:
            raise ValueError("endpoint_model_id 不能为空")
        if self.source not in _MODEL_SOURCES:
            raise ValueError(f"未知模型来源: {self.source}")
        for value, name in (
            (self.context_window_tokens, "context_window_tokens"),
            (self.max_output_tokens, "max_output_tokens"),
        ):
            if value is not None and value <= 0:
                raise ValueError(f"{name} 必须为正整数")
        object.__setattr__(self, "endpoint_model_id", endpoint_model_id)
        object.__setattr__(
            self,
            "display_name",
            self.display_name.strip() or endpoint_model_id,
        )
        if self.canonical_model_id is not None:
            canonical = self.canonical_model_id.strip()
            object.__setattr__(self, "canonical_model_id", canonical or None)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.endpoint_model_id,
            "display_name": self.display_name,
            "source": self.source,
        }
        optional = {
            "canonical_model_id": self.canonical_model_id,
            "context_window_tokens": self.context_window_tokens,
            "max_output_tokens": self.max_output_tokens,
            "supports_tools": self.supports_tools,
            "supports_vision": self.supports_vision,
            "supports_reasoning": self.supports_reasoning,
        }
        result.update({key: value for key, value in optional.items() if value is not None})
        if self.hidden:
            result["hidden"] = True
        return result

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> ProviderModelRecord:
        return cls(
            endpoint_model_id=str(raw.get("id") or ""),
            display_name=str(raw.get("display_name") or ""),
            canonical_model_id=_optional_string(raw.get("canonical_model_id")),
            source=str(raw.get("source") or "manual"),  # type: ignore[arg-type]
            context_window_tokens=_optional_positive_int(
                raw.get("context_window_tokens"),
                "context_window_tokens",
            ),
            max_output_tokens=_optional_positive_int(
                raw.get("max_output_tokens"),
                "max_output_tokens",
            ),
            supports_tools=_optional_bool(raw.get("supports_tools"), "supports_tools"),
            supports_vision=_optional_bool(
                raw.get("supports_vision"),
                "supports_vision",
            ),
            supports_reasoning=_optional_bool(
                raw.get("supports_reasoning"),
                "supports_reasoning",
            ),
            hidden=bool(raw.get("hidden", False)),
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
    models: Tuple[ProviderModelRecord, ...] = ()
    enabled: bool = True
    legacy_provider_id: Optional[str] = None

    def __post_init__(self) -> None:
        if _CONNECTION_ID_PATTERN.fullmatch(self.connection_id) is None:
            raise ValueError(f"无效 connection_id: {self.connection_id!r}")
        if _ID_PATTERN.fullmatch(self.catalog_id) is None:
            raise ValueError(f"无效 catalog_id: {self.catalog_id!r}")
        alias = self.alias.strip()
        if not alias:
            raise ValueError("alias 不能为空")
        model_ids = [model.endpoint_model_id for model in self.models]
        if len(set(model_ids)) != len(model_ids):
            raise ValueError("连接中的模型 ID 不能重复")
        object.__setattr__(self, "alias", alias)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "catalog_id": self.catalog_id,
            "alias": self.alias,
            "enabled": self.enabled,
        }
        optional = {
            "api_base": self.api_base,
            "api_mode": self.api_mode,
            "auth_type": self.auth_type,
            "credential_ref": self.credential_ref,
            "legacy_provider_id": self.legacy_provider_id,
        }
        result.update({key: value for key, value in optional.items() if value})
        result["models"] = [model.to_dict() for model in self.models]
        return result

    @classmethod
    def from_dict(
        cls,
        connection_id: str,
        raw: Mapping[str, Any],
    ) -> ProviderConnection:
        raw_models = raw.get("models", [])
        if not isinstance(raw_models, list):
            raise ValueError("models 必须是数组")
        return cls(
            connection_id=connection_id,
            catalog_id=str(raw.get("catalog_id") or ""),
            alias=str(raw.get("alias") or ""),
            api_base=str(raw.get("api_base") or ""),
            api_mode=str(raw.get("api_mode") or ""),
            auth_type=str(raw.get("auth_type") or ""),
            credential_ref=str(raw.get("credential_ref") or ""),
            models=tuple(
                ProviderModelRecord.from_dict(model)
                for model in raw_models
                if isinstance(model, Mapping)
            ),
            enabled=bool(raw.get("enabled", True)),
            legacy_provider_id=_optional_string(raw.get("legacy_provider_id")),
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
                connection_id: connection.to_dict()
                for connection_id, connection in self.connections.items()
            },
        }


class ProviderConnectionStore:
    """Atomically read and write stable Provider connection instances."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or get_provider_config_path()
        self._uses_default_path = path is None

    def load(self) -> ProviderConnectionDocument:
        raw = read_yaml_mapping(self.path)
        if not raw:
            return ProviderConnectionDocument()
        version = raw.get("version", 1)
        if version == 1:
            document = self._migrate_v1(raw)
            backup = self.path.with_suffix(f"{self.path.suffix}.v1.bak")
            if self.path.exists() and not backup.exists():
                shutil.copy2(self.path, backup)
            self.save(document)
            return document
        if version != CONNECTION_DOCUMENT_VERSION:
            raise ProviderConnectionStoreError(
                f"不支持的 Provider 连接配置版本: {version!r}"
            )
        return _parse_document(raw)

    def save(self, document: ProviderConnectionDocument) -> None:
        if self._uses_default_path:
            ensure_elfie_home()
        write_yaml_mapping(self.path, document.to_dict())

    def create(
        self,
        *,
        catalog_id: str,
        alias: str,
        api_base: str = "",
        api_mode: str = "",
        auth_type: str = "",
        credential_ref: str = "",
        models: Tuple[ProviderModelRecord, ...] = (),
        legacy_provider_id: Optional[str] = None,
    ) -> ProviderConnection:
        document = self.load()
        next_value = document.counters.get(catalog_id, 0) + 1
        connection_id = f"{catalog_id}_{next_value:04d}"
        while connection_id in document.connections:
            next_value += 1
            connection_id = f"{catalog_id}_{next_value:04d}"
        connection = ProviderConnection(
            connection_id=connection_id,
            catalog_id=catalog_id,
            alias=alias,
            api_base=api_base,
            api_mode=api_mode,
            auth_type=auth_type,
            credential_ref=credential_ref,
            models=models,
            legacy_provider_id=legacy_provider_id,
        )
        connections = dict(document.connections)
        connections[connection_id] = connection
        counters = dict(document.counters)
        counters[catalog_id] = next_value
        self.save(ProviderConnectionDocument(counters=counters, connections=connections))
        return connection

    def replace(self, connection: ProviderConnection) -> None:
        document = self.load()
        connections = dict(document.connections)
        connections[connection.connection_id] = connection
        counters = dict(document.counters)
        match = _CONNECTION_ID_PATTERN.fullmatch(connection.connection_id)
        assert match is not None
        counters[connection.catalog_id] = max(
            counters.get(connection.catalog_id, 0),
            int(match.group(2)),
        )
        self.save(ProviderConnectionDocument(counters=counters, connections=connections))

    def delete(self, connection_id: str) -> bool:
        document = self.load()
        if connection_id not in document.connections:
            return False
        connections = dict(document.connections)
        del connections[connection_id]
        self.save(
            ProviderConnectionDocument(
                counters=dict(document.counters),
                connections=connections,
            )
        )
        return True

    def _migrate_v1(
        self,
        raw: Mapping[str, Any],
    ) -> ProviderConnectionDocument:
        raw_providers = raw.get("providers", {})
        if not isinstance(raw_providers, Mapping):
            raise ProviderConnectionStoreError("旧版 providers 必须是对象")
        counters: Dict[str, int] = {}
        connections: Dict[str, ProviderConnection] = {}
        for legacy_id, raw_provider in raw_providers.items():
            if not isinstance(legacy_id, str) or not isinstance(raw_provider, Mapping):
                raise ProviderConnectionStoreError("旧版 Provider 配置不合法")
            catalog_id = _LEGACY_CATALOG_IDS.get(legacy_id, "custom_openai")
            next_value = counters.get(catalog_id, 0) + 1
            counters[catalog_id] = next_value
            connection_id = f"{catalog_id}_{next_value:04d}"
            connections[connection_id] = _migrate_provider(
                connection_id,
                catalog_id,
                legacy_id,
                raw_provider,
            )
        return ProviderConnectionDocument(counters=counters, connections=connections)


def _parse_document(raw: Mapping[str, Any]) -> ProviderConnectionDocument:
    raw_counters = raw.get("connection_counters", {})
    raw_connections = raw.get("connections", {})
    if not isinstance(raw_counters, Mapping) or not isinstance(raw_connections, Mapping):
        raise ProviderConnectionStoreError(
            "connection_counters 和 connections 必须是对象"
        )
    counters: Dict[str, int] = {}
    for catalog_id, value in raw_counters.items():
        if not isinstance(catalog_id, str) or _ID_PATTERN.fullmatch(catalog_id) is None:
            raise ProviderConnectionStoreError(f"无效 catalog_id: {catalog_id!r}")
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ProviderConnectionStoreError(f"无效连接序号: {catalog_id}")
        counters[catalog_id] = value
    connections: Dict[str, ProviderConnection] = {}
    try:
        for connection_id, value in raw_connections.items():
            if not isinstance(connection_id, str) or not isinstance(value, Mapping):
                raise ValueError("连接配置必须是对象")
            connection = ProviderConnection.from_dict(connection_id, value)
            connections[connection_id] = connection
    except ValueError as exc:
        raise ProviderConnectionStoreError(str(exc)) from exc
    return ProviderConnectionDocument(counters=counters, connections=connections)


def _migrate_provider(
    connection_id: str,
    catalog_id: str,
    legacy_id: str,
    raw: Mapping[str, Any],
) -> ProviderConnection:
    raw_models = raw.get("models", [])
    models = []
    if isinstance(raw_models, list):
        for item in raw_models:
            if isinstance(item, Mapping):
                model_id = str(item.get("id") or item.get("name") or "").strip()
                if model_id:
                    models.append(
                        ProviderModelRecord(
                            endpoint_model_id=model_id,
                            display_name=str(item.get("display_name") or model_id),
                            source="manual",
                        )
                    )
            elif str(item).strip():
                models.append(ProviderModelRecord(endpoint_model_id=str(item).strip()))
    return ProviderConnection(
        connection_id=connection_id,
        catalog_id=catalog_id,
        alias=str(raw.get("display_name") or legacy_id),
        api_base=str(raw.get("api_base") or ""),
        api_mode=str(raw.get("api_mode") or ""),
        auth_type=str(raw.get("auth_type") or ""),
        credential_ref=str(raw.get("api_key_env") or ""),
        models=tuple(models),
        legacy_provider_id=legacy_id,
    )


def _optional_string(value: Any) -> Optional[str]:
    normalized = str(value or "").strip()
    return normalized or None


def _optional_positive_int(value: Any, field_name: str) -> Optional[int]:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field_name} 必须为正整数")
    return value


def _optional_bool(value: Any, field_name: str) -> Optional[bool]:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} 必须为布尔值")
    return value
