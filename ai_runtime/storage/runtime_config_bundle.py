"""Runtime and Tool configuration storage with a read-only Provider projection."""

from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any, Mapping

from ai_runtime.storage.config_store import read_yaml_mapping, write_yaml_mapping
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


def read_runtime_config_bundle() -> dict[str, Any]:
    """读取并合并正式 Runtime 配置，保持既有调用方数据形状。"""
    runtime_path = get_config_path()
    tool_path = get_tool_config_path()

    config = copy.deepcopy(read_yaml_mapping(runtime_path))
    config.pop("version", None)
    config.pop("providers", None)

    runtime_policy = config.get("runtime_policy")
    if isinstance(runtime_policy, dict):
        runtime_policy.pop("tools", None)

    if tool_path.exists():
        tool_document = read_yaml_mapping(tool_path)
        runtime_policy = config.get("runtime_policy")
        if not isinstance(runtime_policy, dict):
            runtime_policy = {}
            config["runtime_policy"] = runtime_policy
        runtime_policy["tools"] = copy.deepcopy(tool_document.get("tools", {}))

    return config


def write_runtime_config_bundle(
    config: Mapping[str, Any],
    *,
    backup_existing: bool = True,
) -> None:
    """把合并配置按职责写入三份正式 YAML。"""
    ensure_elfie_home()
    safe_config = copy.deepcopy(dict(config))
    safe_config.pop("providers", None)
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

    runtime_document = {
        "version": CONFIG_DOCUMENT_VERSION,
        **safe_config,
    }
    tool_document = {
        "version": CONFIG_DOCUMENT_VERSION,
        "tools": tools,
    }

    documents = (
        (get_config_path(), runtime_document),
        (get_tool_config_path(), tool_document),
    )
    for path, document in documents:
        if read_yaml_mapping(path) == document:
            continue
        if backup_existing:
            _backup(path)
        write_yaml_mapping(path, document)
