"""Runtime 本地 YAML 配置存储。

运行时配置属于用户数据，统一保存在 ``~/.elfienest``，不写入源码目录。
写入采用同目录临时文件替换，避免进程中断留下半个 YAML 文件。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

import yaml


class ConfigStoreError(RuntimeError):
    """本地配置无法读取或写入。"""


def read_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as file:
            loaded = yaml.safe_load(file) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigStoreError(f"无法读取配置文件 {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ConfigStoreError(f"配置文件 {path} 的顶层必须是对象")
    return loaded


def write_yaml_mapping(
    path: Path,
    data: Mapping[str, Any],
    *,
    mode: int = 0o600,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as file:
            yaml.safe_dump(
                dict(data),
                file,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            )
        if os.name != "nt":
            os.chmod(temp_path, mode)
        temp_path.replace(path)
    except OSError as exc:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise ConfigStoreError(f"无法写入配置文件 {path}: {exc}") from exc
