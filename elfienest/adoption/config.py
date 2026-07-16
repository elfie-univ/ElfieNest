"""领养配置共享模块 — 从 system.adoption 读取动态配置。

所有函数在调用时重新读取 ``~/.elfienest/config.yaml``（不缓存），
确保配置更改即时生效。

与 ``system_routes.py`` 使用相同的配置文件路径和默认值，
通过 ``_RUNTIME_CONFIG_PATH`` 使之在测试中可 mock。

Usage::

    from elfienest.adoption.config import get_max_elfies_per_user, get_allowed_anatomy_types

    limit = get_max_elfies_per_user()
    types = get_allowed_anatomy_types()
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from elfienest.config.runtime_store import read_runtime_config
from runtime.storage.data_home import get_config_path

_RUNTIME_CONFIG_PATH: Path = get_config_path()
_DEFAULT_RUNTIME_CONFIG_PATH: Path = _RUNTIME_CONFIG_PATH


def _load_adoption_settings() -> dict:
    """从当前 YAML 配置读取 adoption 设置，与默认值深层合并。"""
    from runtime.config import DEFAULT_SYSTEM_SETTINGS, deep_update  # noqa: PLC0415

    base: Dict[str, Any] = copy.deepcopy(DEFAULT_SYSTEM_SETTINGS)
    configured_path = _config_path()
    if not configured_path.exists():
        return base.get("adoption", {})

    saved = read_runtime_config(configured_path)
    if not isinstance(saved, dict):
        return base.get("adoption", {})

    saved_system = saved.get("system", {})
    if isinstance(saved_system, dict):
        deep_update(base, saved_system)

    return base.get("adoption", {})


def _config_path() -> Path:
    """返回运行时配置路径；测试可显式注入临时路径。"""
    if _RUNTIME_CONFIG_PATH != _DEFAULT_RUNTIME_CONFIG_PATH:
        return _RUNTIME_CONFIG_PATH
    return get_config_path()


def get_adoption_settings(db_path: Optional[str] = None) -> dict:
    """获取领养配置（deep-merged defaults）。

    Args:
        db_path: 数据库路径（未使用，保留接口一致性）

    Returns:
        合并后的 system.adoption 配置字典
    """
    _ = db_path
    return _load_adoption_settings()


def get_max_elfies_per_user(db_path: Optional[str] = None) -> int:
    """获取每用户最大精灵数。

    默认值：3（与旧硬编码一致）。
    """
    settings = get_adoption_settings(db_path)
    return int(settings.get("max_elfies_per_user", 3))


def get_allowed_anatomy_types(
    db_path: Optional[str] = None,
) -> Tuple[str, ...]:
    """获取允许的解剖类型列表。

    默认值：``("biped", "quadruped")``（与旧硬编码一致）。

    Returns:
        允许的 anatomy_type 元组
    """
    settings = get_adoption_settings(db_path)
    raw = settings.get("allowed_anatomy_types", ["biped", "quadruped"])
    return tuple(raw)


def get_allowed_personality_styles(
    db_path: Optional[str] = None,
) -> Dict[str, dict]:
    """获取启用的性格预设。

    从 ``personality_presets_enabled`` 配置过滤 ``PERSONALITY_PRESETS``，
    仅返回启用的预设。如果全部禁用，返回全部预设（安全回退）。

    Returns:
        ``{preset_name: preset_data}`` 字典
    """
    settings = get_adoption_settings(db_path)
    enabled = settings.get("personality_presets_enabled", {})

    # lazy import 避免与 adoption.py 的循环引用
    from elfienest.adoption.generator import PERSONALITY_PRESETS  # noqa: PLC0415

    result: Dict[str, dict] = {}
    for name, preset in PERSONALITY_PRESETS.items():
        if enabled.get(name, True):
            result[name] = preset

    # 安全回退：如果全部禁用，返回全部预设
    if not result:
        return dict(PERSONALITY_PRESETS)

    return result
