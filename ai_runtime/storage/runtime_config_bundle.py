"""正式 Runtime 配置的多文件存储边界。

调用方继续使用原有合并配置结构；只有落盘时才按职责拆分为 Runtime、
Provider 和 Tool 三份 YAML。
"""

from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any, Mapping

from ai_runtime.storage.config_store import read_yaml_mapping, write_yaml_mapping
from ai_runtime.storage.data_home import (
    ensure_elfie_home,
    get_config_path,
    get_provider_config_path,
    get_tool_config_path,
)

CONFIG_DOCUMENT_VERSION = 1


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
    provider_path = get_provider_config_path()
    tool_path = get_tool_config_path()

    config = copy.deepcopy(read_yaml_mapping(runtime_path))
    config.pop("version", None)
    config.pop("providers", None)

    runtime_policy = config.get("runtime_policy")
    if isinstance(runtime_policy, dict):
        runtime_policy.pop("tools", None)

    if provider_path.exists():
        provider_document = read_yaml_mapping(provider_path)
        config["providers"] = copy.deepcopy(provider_document.get("providers", {}))

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
    providers = _without_plaintext_api_keys(safe_config.pop("providers", {}))

    runtime_policy = safe_config.get("runtime_policy")
    tools: Any = {}
    if isinstance(runtime_policy, dict):
        tools = _without_plaintext_api_keys(runtime_policy.pop("tools", {}))

    runtime_document = {
        "version": CONFIG_DOCUMENT_VERSION,
        **safe_config,
    }
    provider_document = {
        "version": CONFIG_DOCUMENT_VERSION,
        "providers": providers,
    }
    tool_document = {
        "version": CONFIG_DOCUMENT_VERSION,
        "tools": tools,
    }

    documents = (
        (get_config_path(), runtime_document),
        (get_provider_config_path(), provider_document),
        (get_tool_config_path(), tool_document),
    )
    if backup_existing:
        for path, _document in documents:
            _backup(path)
    for path, document in documents:
        write_yaml_mapping(path, document)
