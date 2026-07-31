"""Storage boundary for Runtime settings and Tool settings documents."""

from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any, Mapping

from ai_runtime.storage.config_store import (
    ConfigStoreError,
    read_yaml_mapping,
    write_yaml_mapping,
)
from ai_runtime.storage.data_home import (
    ensure_elfie_home,
    get_config_path,
    get_tool_config_path,
)

CONFIG_DOCUMENT_VERSION = 1
_LEGACY_ROUTING_FIELDS = frozenset(
    {
        "cheap_model",
        "cheap_provider",
        "deep_model",
        "deep_provider",
        "multimodal_model",
        "multimodal_provider",
    }
)


def _backup(path: Path) -> None:
    if path.exists():
        shutil.copy2(str(path), str(path.with_suffix(f"{path.suffix}.bak")))


def _without_plaintext_api_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_plaintext_api_keys(item)
            for key, item in value.items()
            if key != "api_key"
        }
    if isinstance(value, list):
        return [_without_plaintext_api_keys(item) for item in value]
    return value


def read_runtime_settings() -> dict[str, Any]:
    """Read Runtime settings with Tool settings projected into the public shape."""
    config = copy.deepcopy(read_yaml_mapping(get_config_path()))
    config.pop("version", None)
    if "providers" in config:
        raise ConfigStoreError(
            "Runtime 设置不接受 providers；请使用 ProviderConnectionStore"
        )

    runtime_policy = config.get("runtime_policy")
    if isinstance(runtime_policy, dict):
        runtime_policy.pop("tools", None)

    tool_path = get_tool_config_path()
    if tool_path.exists():
        tool_document = read_yaml_mapping(tool_path)
        runtime_policy = config.get("runtime_policy")
        if not isinstance(runtime_policy, dict):
            runtime_policy = {}
            config["runtime_policy"] = runtime_policy
        runtime_policy["tools"] = copy.deepcopy(tool_document.get("tools", {}))
    return config


def write_runtime_settings(
    config: Mapping[str, Any],
    *,
    backup_existing: bool = True,
) -> None:
    """Write Runtime and Tool settings without reading or writing Provider data."""
    if "providers" in config:
        raise ConfigStoreError(
            "Runtime 设置不接受 providers；请使用 ProviderConnectionStore"
        )
    ensure_elfie_home()
    safe_config = copy.deepcopy(dict(config))
    for field_name in _LEGACY_ROUTING_FIELDS:
        safe_config.pop(field_name, None)
    system = safe_config.get("system")
    if isinstance(system, dict) and isinstance(system.get("llm"), dict):
        for field_name in (
            "default_cheap_model",
            "default_cheap_provider",
            "default_deep_model",
            "default_deep_provider",
            "default_multimodal_model",
            "default_multimodal_provider",
        ):
            system["llm"].pop(field_name, None)

    runtime_policy = safe_config.get("runtime_policy")
    tools: Any = {}
    if isinstance(runtime_policy, dict):
        tools = _without_plaintext_api_keys(runtime_policy.pop("tools", {}))

    documents = (
        (get_config_path(), {"version": CONFIG_DOCUMENT_VERSION, **safe_config}),
        (
            get_tool_config_path(),
            {"version": CONFIG_DOCUMENT_VERSION, "tools": tools},
        ),
    )
    for path, document in documents:
        if read_yaml_mapping(path) == document:
            continue
        if backup_existing:
            _backup(path)
        write_yaml_mapping(path, document)
