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
from ai_runtime.storage.secrets import (
    provider_secret_name,
    resolve_secret,
    set_provider_secret,
)


def read_runtime_config(path: Path) -> Dict[str, Any]:
    if path.suffix not in {".yaml", ".yml"}:
        raise ConfigStoreError(
            f"生产配置必须使用 ELFIE_HOME/config.yaml，拒绝读取旧格式: {path}"
        )
    return read_yaml_mapping(path)


def hydrate_runtime_secrets(config: Dict[str, Any]) -> Dict[str, Any]:
    """仅供内部调用链使用，返回注入本地密钥的配置副本。"""
    hydrated = copy.deepcopy(config)
    providers = hydrated.get("providers", {})
    if not isinstance(providers, dict):
        return hydrated
    for provider_id, provider in providers.items():
        if not isinstance(provider_id, str) or not isinstance(provider, dict):
            continue
        secret_name = str(
            provider.get("api_key_env") or provider_secret_name(provider_id)
        )
        provider["api_key_env"] = secret_name
        provider["api_key"] = resolve_secret(secret_name)
    return hydrated


def write_runtime_config(
    path: Path,
    config: Dict[str, Any],
    *,
    backup_existing: bool = True,
) -> None:
    if path.suffix not in {".yaml", ".yml"}:
        raise ConfigStoreError(
            f"生产配置必须使用 ELFIE_HOME/config.yaml，拒绝写入旧格式: {path}"
        )
    if backup_existing and path.exists():
        backup_path = path.with_suffix(f"{path.suffix}.bak")
        shutil.copy2(str(path), str(backup_path))

    safe_config = copy.deepcopy(config)
    providers = safe_config.get("providers", {})
    if isinstance(providers, dict):
        for provider_id, provider in providers.items():
            if not isinstance(provider_id, str) or not isinstance(provider, dict):
                continue
            has_api_key_field = "api_key" in provider
            api_key = str(provider.pop("api_key", "") or "")
            secret_name = str(
                provider.get("api_key_env") or provider_secret_name(provider_id)
            )
            provider["api_key_env"] = secret_name
            if has_api_key_field:
                set_provider_secret(provider_id, api_key)
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
