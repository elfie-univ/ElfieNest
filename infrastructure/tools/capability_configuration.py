"""Runtime configuration Adapter for the Capabilities Feature Port."""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
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
from infrastructure.tools.execution.config import default_tool_configs

DocumentReader = Callable[[Path], Mapping[str, JsonValue]]
DocumentWriter = Callable[[Path, Mapping[str, JsonValue]], None]
ToolDefaults = Callable[[], Mapping[str, Mapping[str, JsonValue]]]

_SEARCH_PROVIDERS = frozenset({"duckduckgo", "brave", "tavily"})


class RuntimeCapabilitiesAdapter:
    """Read and atomically update the sole logical ``runtime_policy.tools`` fact."""

    def __init__(
        self,
        config_path: Path,
        *,
        read_document: DocumentReader,
        write_document: DocumentWriter,
        defaults: ToolDefaults = default_tool_configs,
    ) -> None:
        self._config_path = config_path
        self._read_document_impl = read_document
        self._write_document_impl = write_document
        self._defaults = defaults

    def load_capabilities(self) -> StoredCapabilities:
        try:
            document = self._read_document()
            runtime_policy = self._mapping_value(
                document.get("runtime_policy", {}), "runtime_policy"
            )
            effective = self._effective_configs(runtime_policy)
            web = self._mapping_value(effective.get("web_search"), "web_search")
            local = self._mapping_value(effective.get("local_file"), "local_file")
            provider = self._string(web, "provider")
            if provider not in _SEARCH_PROVIDERS:
                raise CapabilitiesPortError(
                    "runtime_policy.tools.web_search.provider 无效"
                )
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
            runtime_policy = self._mutable_mapping(
                document.get("runtime_policy", {}), "runtime_policy"
            )
            tools = self._mutable_mapping(runtime_policy.get("tools", {}), "tools")
            current = self._mutable_mapping(
                tools.get(capability_key, {}), capability_key
            )
            current.update(values)
            tools[capability_key] = current
            runtime_policy["tools"] = tools
            document["runtime_policy"] = runtime_policy
            self._write_document(document)
        except CapabilitiesPortError:
            raise
        except (OSError, TypeError, ValueError) as error:
            raise CapabilitiesPortError("无法保存系统能力配置") from error

    def _read_document(self) -> dict[str, JsonValue]:
        return self._mutable_mapping(
            cast(JsonValue, self._read_document_impl(self._config_path)),
            "configuration",
        )

    def _write_document(self, document: Mapping[str, JsonValue]) -> None:
        self._write_document_impl(self._config_path, copy.deepcopy(dict(document)))

    @staticmethod
    def _mapping_value(value: JsonValue, field: str) -> Mapping[str, JsonValue]:
        if not isinstance(value, Mapping):
            raise CapabilitiesPortError(f"{field} 必须是对象")
        if not all(isinstance(key, str) for key in value):
            raise CapabilitiesPortError(f"{field} 的字段名必须是字符串")
        return cast(Mapping[str, JsonValue], value)

    def _effective_configs(
        self, runtime_policy: Mapping[str, JsonValue]
    ) -> dict[str, dict[str, JsonValue]]:
        raw_defaults = cast(JsonValue, self._defaults())
        defaults = self._mapping_value(raw_defaults, "capability defaults")
        raw_tools = self._mapping_value(runtime_policy.get("tools", {}), "tools")
        effective: dict[str, dict[str, JsonValue]] = {}
        for capability_key in ("web_search", "local_file"):
            current = self._mutable_mapping(
                defaults.get(capability_key), f"default {capability_key}"
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
