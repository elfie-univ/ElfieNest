"""Runtime configuration Adapter for the Capabilities Feature Port."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from pathlib import Path
from typing import FrozenSet, cast

from pydantic import JsonValue

from app.features.configuration.capabilities import (
    CapabilitiesPortError,
    LocalFileUpdateField,
    SearchProvider,
    StoredCapabilities,
    StoredLocalFileCapability,
    StoredWebSearchCapability,
    WebSearchUpdateField,
)
from infrastructure.persistence.configuration.config_store import (
    ConfigStoreError,
    read_yaml_mapping,
    write_yaml_mapping,
)
from infrastructure.persistence.configuration.documents import (
    ConfigDocumentError,
    ConfigDocumentId,
    RuntimeConfigSource,
)
from infrastructure.persistence.layout.data_home import (
    get_configs_dir,
    get_tool_config_path,
)
from infrastructure.tools.execution.config import default_tool_configs

_SEARCH_PROVIDERS = frozenset({"duckduckgo", "brave", "tavily"})


class RuntimeCapabilitiesAdapter:
    """Read and atomically update the dedicated user ``tools.yaml`` document."""

    def __init__(
        self,
        config_path: Path,
        *,
        defaults: Mapping[str, Mapping[str, JsonValue]] | None = None,
    ) -> None:
        self._config_path = config_path
        self._defaults = defaults or default_tool_configs()

    def load_capabilities(self) -> StoredCapabilities:
        try:
            document = self._read_document()
            raw_tools = self._mapping_value(document.get("tools", {}), "tools")
            effective = self._effective_configs(raw_tools)
            web = self._mapping_value(effective.get("web_search"), "web_search")
            local = self._mapping_value(effective.get("local_file"), "local_file")
            provider = self._string(web, "provider")
            if provider not in _SEARCH_PROVIDERS:
                raise CapabilitiesPortError("tools.web_search.provider 无效")
            return StoredCapabilities(
                web_search=StoredWebSearchCapability(
                    enabled=self._boolean(web, "enabled"),
                    provider=cast(SearchProvider, provider),
                    api_base=self._string(web, "api_base"),
                    credential_ref=self._string(web, "api_key_env"),
                    max_results=self._integer(web, "max_results"),
                    max_result_bytes=self._integer(web, "max_result_bytes"),
                    timeout_seconds=self._number(web, "timeout_seconds"),
                    max_tool_calls=self._integer(web, "max_tool_calls"),
                    max_total_result_bytes=self._integer(web, "max_total_result_bytes"),
                ),
                local_file=StoredLocalFileCapability(
                    enabled=self._boolean(local, "enabled"),
                    root=self._string(local, "root"),
                    root_policy=self._string(local, "root_policy"),
                    max_read_bytes=self._integer(local, "max_read_bytes"),
                    max_items=self._integer(local, "max_items"),
                    max_result_bytes=self._integer(local, "max_result_bytes"),
                    max_tool_calls=self._integer(local, "max_tool_calls"),
                    max_total_result_bytes=self._integer(
                        local, "max_total_result_bytes"
                    ),
                ),
            )
        except CapabilitiesPortError:
            raise
        except (OSError, TypeError, ValueError) as error:
            raise CapabilitiesPortError("系统能力配置不可用") from error

    def save_web_search(
        self,
        capability: StoredWebSearchCapability,
        fields: FrozenSet[WebSearchUpdateField],
    ) -> StoredCapabilities:
        values: dict[str, JsonValue] = {"api_key_env": capability.credential_ref}
        if "enabled" in fields:
            values["enabled"] = capability.enabled
        if "provider" in fields:
            values["provider"] = capability.provider
        if "api_base" in fields:
            values["api_base"] = capability.api_base
        if "max_results" in fields:
            values["max_results"] = capability.max_results
        if "max_result_bytes" in fields:
            values["max_result_bytes"] = capability.max_result_bytes
        self._update_capability("web_search", values)
        return self.load_capabilities()

    def save_local_file(
        self,
        capability: StoredLocalFileCapability,
        fields: FrozenSet[LocalFileUpdateField],
    ) -> StoredCapabilities:
        values: dict[str, JsonValue] = {}
        if "enabled" in fields:
            values["enabled"] = capability.enabled
        if "max_read_bytes" in fields:
            values["max_read_bytes"] = capability.max_read_bytes
        self._update_capability("local_file", values)
        return self.load_capabilities()

    def _update_capability(
        self,
        capability_key: str,
        values: Mapping[str, JsonValue],
    ) -> None:
        try:
            document = self._read_document()
            tools = self._mutable_mapping(document.get("tools", {}), "tools")
            current = self._mutable_mapping(
                tools.get(capability_key, {}), capability_key
            )
            current.update(values)
            tools[capability_key] = current
            document["tools"] = tools
            self._write_document(document)
        except CapabilitiesPortError:
            raise
        except (
            ConfigDocumentError,
            ConfigStoreError,
            OSError,
            TypeError,
            ValueError,
        ) as error:
            raise CapabilitiesPortError("无法保存系统能力配置") from error

    def _read_document(self) -> dict[str, JsonValue]:
        try:
            if self._config_path == get_tool_config_path():
                registered = RuntimeConfigSource(get_configs_dir()).load(
                    ConfigDocumentId.TOOL_SETTINGS
                )
                document = {} if registered is None else registered.document
            else:
                document = read_yaml_mapping(self._config_path)
            return self._mutable_mapping(cast(JsonValue, document), "configuration")
        except (ConfigDocumentError, ConfigStoreError) as error:
            raise CapabilitiesPortError("系统能力配置不可用") from error

    def _write_document(self, document: Mapping[str, JsonValue]) -> None:
        payload = {"version": 1, **copy.deepcopy(dict(document))}
        if self._config_path == get_tool_config_path():
            RuntimeConfigSource(get_configs_dir()).write(
                ConfigDocumentId.TOOL_SETTINGS,
                payload,
            )
            return
        write_yaml_mapping(self._config_path, payload)

    @staticmethod
    def _mapping_value(value: JsonValue, field: str) -> Mapping[str, JsonValue]:
        if not isinstance(value, Mapping):
            raise CapabilitiesPortError(f"{field} 必须是对象")
        if not all(isinstance(key, str) for key in value):
            raise CapabilitiesPortError(f"{field} 的字段名必须是字符串")
        return cast(Mapping[str, JsonValue], value)

    def _effective_configs(
        self, raw_tools: Mapping[str, JsonValue]
    ) -> dict[str, dict[str, JsonValue]]:
        defaults = self._defaults
        effective: dict[str, dict[str, JsonValue]] = {}
        for capability_key in ("web_search", "local_file"):
            default = defaults.get(capability_key)
            if default is None:
                raise CapabilitiesPortError(f"default {capability_key} 必须是对象")
            current = self._mutable_mapping(
                cast(JsonValue, default), f"default {capability_key}"
            )
            raw_capability = raw_tools.get(capability_key)
            if raw_capability is not None:
                current.update(self._mutable_mapping(raw_capability, capability_key))
            effective[capability_key] = current
        return effective

    @classmethod
    def _mutable_mapping(cls, value: JsonValue, field: str) -> dict[str, JsonValue]:
        return copy.deepcopy(dict(cls._mapping_value(value, field)))

    @staticmethod
    def _boolean(values: Mapping[str, JsonValue], field: str) -> bool:
        value = values.get(field)
        if not isinstance(value, bool):
            raise CapabilitiesPortError(f"{field} 必须是布尔值")
        return value

    @staticmethod
    def _integer(values: Mapping[str, JsonValue], field: str) -> int:
        value = values.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            raise CapabilitiesPortError(f"{field} 必须是整数")
        return value

    @staticmethod
    def _number(values: Mapping[str, JsonValue], field: str) -> float:
        value = values.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise CapabilitiesPortError(f"{field} 必须是数字")
        return float(value)

    @staticmethod
    def _string(values: Mapping[str, JsonValue], field: str) -> str:
        value = values.get(field)
        if not isinstance(value, str):
            raise CapabilitiesPortError(f"{field} 必须是字符串")
        return value


__all__ = ("RuntimeCapabilitiesAdapter",)
