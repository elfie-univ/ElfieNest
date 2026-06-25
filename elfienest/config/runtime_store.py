from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any, Dict

from runtime.config import DEFAULT_SYSTEM_SETTINGS, deep_update


def read_runtime_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as file:
            loaded = json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def write_runtime_config(
    path: Path,
    config: Dict[str, Any],
    *,
    backup_existing: bool = True,
) -> None:
    if backup_existing and path.exists():
        shutil.copy2(str(path), str(path.with_suffix(".json.bak")))

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
