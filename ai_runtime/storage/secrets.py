"""Provider 密钥的本地安全存储。

密钥只保存在 ``~/.elfienest/.env``。普通配置仅保存环境变量名，API 和
日志只能暴露 ``has_api_key``，不得返回明文值。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Mapping

from ai_runtime.providers.profiles import get_profile
from ai_runtime.storage.data_home import get_env_path

_ENV_NAME_PATTERN = re.compile(r"[^A-Z0-9_]+")


def provider_secret_name(provider_id: str) -> str:
    profile = get_profile(provider_id)
    if profile and profile.api_key_env_var:
        return profile.api_key_env_var
    normalized = _ENV_NAME_PATTERN.sub("_", provider_id.upper()).strip("_")
    return f"{normalized or 'CUSTOM'}_API_KEY"


def tool_secret_name(tool_id: str) -> str:
    normalized = _ENV_NAME_PATTERN.sub("_", tool_id.upper()).strip("_")
    return f"ELFIE_{normalized or 'TOOL'}_API_KEY"


def read_secrets(path: Path | None = None) -> dict[str, str]:
    secret_path = path or get_env_path()
    if not secret_path.exists():
        return {}
    values: dict[str, str] = {}
    try:
        with secret_path.open(encoding="utf-8") as file:
            for raw_line in file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                normalized_key = key.strip()
                if normalized_key:
                    values[normalized_key] = value.strip()
    except OSError:
        return {}
    return values


def resolve_secret(name: str, path: Path | None = None) -> str:
    return os.getenv(name, read_secrets(path).get(name, ""))


def write_secrets(values: Mapping[str, str], path: Path | None = None) -> None:
    secret_path = path or get_env_path()
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = secret_path.with_name(f".{secret_path.name}.tmp")
    sanitized: dict[str, str] = {}
    for key, value in values.items():
        normalized_key = key.strip()
        if not normalized_key or "\n" in normalized_key or "=" in normalized_key:
            raise ValueError(f"无效的环境变量名: {key!r}")
        normalized_value = str(value)
        if "\n" in normalized_value or "\r" in normalized_value:
            raise ValueError(f"密钥 {normalized_key} 不能包含换行")
        sanitized[normalized_key] = normalized_value

    with temp_path.open("w", encoding="utf-8") as file:
        file.write("# ElfieNest local secrets. Never commit this file.\n")
        for key in sorted(sanitized):
            file.write(f"{key}={sanitized[key]}\n")
    if os.name != "nt":
        os.chmod(temp_path, 0o600)
    temp_path.replace(secret_path)


def set_provider_secret(
    provider_id: str,
    api_key: str,
    path: Path | None = None,
) -> str:
    name = provider_secret_name(provider_id)
    values = read_secrets(path)
    if api_key:
        values[name] = api_key
    else:
        values.pop(name, None)
    write_secrets(values, path)
    return name


def set_tool_secret(tool_id: str, api_key: str, path: Path | None = None) -> str:
    name = tool_secret_name(tool_id)
    values = read_secrets(path)
    if api_key:
        values[name] = api_key
    else:
        values.pop(name, None)
    write_secrets(values, path)
    return name


def redact_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "****"
    return f"****{value[-4:]}"
