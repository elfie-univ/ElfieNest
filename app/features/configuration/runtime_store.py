from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any, Dict

from ai_runtime.config import DEFAULT_SYSTEM_SETTINGS, deep_update
from ai_runtime.storage.config_store import (
    ConfigStoreError,
    read_yaml_mapping,
    write_yaml_mapping,
)
from ai_runtime.storage.data_home import get_config_path
from ai_runtime.storage.runtime_settings import (
    read_runtime_settings,
    write_runtime_settings,
)


def read_runtime_config(path: Path) -> Dict[str, Any]:
    if path.suffix not in {".yaml", ".yml"}:
        raise ConfigStoreError(
            f"生产配置必须使用 ELFIE_HOME/configs/runtime.yaml，拒绝读取旧格式: {path}"
        )
    if path == get_config_path():
        return read_runtime_settings()
    return read_yaml_mapping(path)


def write_runtime_config(
    path: Path,
    config: Dict[str, Any],
    *,
    backup_existing: bool = True,
) -> None:
    if path.suffix not in {".yaml", ".yml"}:
        raise ConfigStoreError(
            f"生产配置必须使用 ELFIE_HOME/configs/runtime.yaml，拒绝写入旧格式: {path}"
        )
    if "providers" in config:
        raise ConfigStoreError(
            "Runtime 设置不接受 providers；请使用 ProviderConnectionStore"
        )
    is_production_bundle = path == get_config_path()
    if is_production_bundle:
        write_runtime_settings(
            config,
            backup_existing=backup_existing,
        )
        return
    if backup_existing and path.exists() and not is_production_bundle:
        backup_path = path.with_suffix(f"{path.suffix}.bak")
        shutil.copy2(str(path), str(backup_path))

    safe_config = copy.deepcopy(config)
    write_yaml_mapping(path, safe_config)


def read_system_section(path: Path, section: str) -> Dict[str, Any]:
    base = copy.deepcopy(DEFAULT_SYSTEM_SETTINGS.get(section, {}))
    saved = read_runtime_config(path)
    saved_section = saved.get("system", {}).get(section, {})
    if isinstance(saved_section, dict):
        deep_update(base, saved_section)
    if section == "adoption":
        base.pop("allowed_anatomy_types", None)
    return base


def write_system_section(
    path: Path,
    section: str,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    full_config = read_runtime_config(path)
    system_config = full_config.setdefault("system", {})
    if not isinstance(system_config, dict):
        system_config = {}
        full_config["system"] = system_config

    current_section = system_config.get(section, {})
    if not isinstance(current_section, dict):
        current_section = {}
    deep_update(current_section, data)
    system_config[section] = current_section

    write_runtime_config(path, full_config)
    return read_system_section(path, section)
