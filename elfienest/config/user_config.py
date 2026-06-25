from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from runtime.data_home import get_config_path, get_env_path

UserConfig = Dict[str, Any]
EnvVars = Dict[str, str]


def read_user_config(path: Optional[Path] = None) -> UserConfig:
    config_path = path or get_config_path()
    if not config_path.exists():
        return {}

    try:
        with open(config_path, encoding="utf-8") as file:
            loaded = yaml.safe_load(file)
    except (OSError, yaml.YAMLError):
        return {}

    return loaded if isinstance(loaded, dict) else {}


def write_user_config(config: UserConfig, path: Optional[Path] = None) -> None:
    config_path = path or get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as file:
        yaml.dump(config, file, allow_unicode=True, default_flow_style=False)


def read_env_file(path: Optional[Path] = None) -> EnvVars:
    env_path = path or get_env_path()
    env_vars: EnvVars = {}
    if not env_path.exists():
        return env_vars

    with open(env_path, encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env_vars[key.strip()] = value.strip()

    return env_vars


def write_env_file(env_vars: EnvVars, path: Optional[Path] = None) -> None:
    env_path = path or get_env_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    with open(env_path, "w", encoding="utf-8") as file:
        file.write("# ElfieNest 环境变量 - API Keys\n")
        file.write("# 此文件已 gitignore，请勿提交到版本库\n\n")
        for key, value in sorted(env_vars.items()):
            file.write(f"{key}={value}\n")
    if os.name == "posix":
        os.chmod(env_path, 0o600)
