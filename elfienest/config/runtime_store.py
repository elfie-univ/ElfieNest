from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any, Dict

from runtime.config import DEFAULT_SYSTEM_SETTINGS, deep_update
from runtime.storage.config_store import read_yaml_mapping, write_yaml_mapping
from runtime.storage.secrets import (
    provider_secret_name,
    resolve_secret,
    set_provider_secret,
)


def read_runtime_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    if path.suffix in {".yaml", ".yml"}:
        try:
            return read_yaml_mapping(path)
        except RuntimeError:
            return {}
    try:
        with open(path, encoding="utf-8") as file:
            loaded = json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


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
    if backup_existing and path.exists():
        shutil.copy2(str(path), str(path.with_suffix(f"{path.suffix}.bak")))

    if path.suffix in {".yaml", ".yml"}:
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
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)


def read_system_section(path: Path, section: str) -> Dict[str, Any]:
    base = copy.deepcopy(DEFAULT_SYSTEM_SETTINGS.get(section, {}))
    saved = read_runtime_config(path)
    saved_section = saved.get("system", {}).get(section, {})
    if isinstance(saved_section, dict):
        deep_update(base, saved_section)
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
