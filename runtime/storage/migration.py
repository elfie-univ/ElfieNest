"""ElfieNest 数据目录迁移 — 从旧 ``data/`` 目录迁移到 ``~/.elfienest/``。

迁移策略：
1. 如果 ``~/.elfienest/`` 已存在 → 已迁移，直接返回
2. 如果旧 ``data/`` 目录存在 → 复制所有内容到 ``~/.elfienest/``
3. 如果旧 ``runtime/runtime_config.json`` 存在 → 转换为 ``~/.elfienest/config.yaml``
4. 如果两者都不存在 → 创建空的 ``~/.elfienest/`` 结构
5. 在旧 ``data/`` 目录中创建 ``.migrated`` 标记文件（不删除旧数据）

版本化配置迁移框架：
- ``migrate_config()`` 读取 config.yaml 中的 config_version
- 按版本号顺序应用迁移函数
- 每个迁移函数是一个 ``Callable[[dict], dict]``，接收并返回配置字典
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from runtime.storage.data_home import ensure_elfie_home, get_config_path, get_elfie_home

logger = logging.getLogger("runtime.storage.migration")

# ---------------------------------------------------------------------------
# 项目根目录下的旧路径
# ---------------------------------------------------------------------------

_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
_OLD_DATA_DIR: Path = _PROJECT_ROOT / "data"
_OLD_RUNTIME_CONFIG: Path = _PROJECT_ROOT / "runtime" / "runtime_config.json"


# ---------------------------------------------------------------------------
# 版本化配置迁移注册表
# ---------------------------------------------------------------------------

# 每个迁移函数签名: (dict) -> dict，接收旧配置，返回新配置
_CONFIG_MIGRATIONS: Dict[int, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}

# 当前配置版本号（供外部和测试引用）
CURRENT_CONFIG_VERSION: int = max(_CONFIG_MIGRATIONS.keys()) if _CONFIG_MIGRATIONS else 1


def register_config_migration(version: int):
    """装饰器：注册配置迁移函数。

    Usage::

        @register_config_migration(2)
        def migrate_v1_to_v2(config: dict) -> dict:
            config.setdefault("new_field", "default_value")
            return config
    """
    def decorator(func: Callable[[Dict[str, Any]], Dict[str, Any]]):
        _CONFIG_MIGRATIONS[version] = func
        return func
    return decorator


@register_config_migration(1)
def _migrate_v0_to_v1(config: Dict[str, Any]) -> Dict[str, Any]:
    """v0 → v1: 初始配置 schema，添加 config_version 字段。"""
    config.setdefault("config_version", 1)
    return config


# ---------------------------------------------------------------------------
# 数据目录迁移
# ---------------------------------------------------------------------------


def migrate_data_home() -> bool:
    """主迁移函数：将旧数据目录迁移到 ``~/.elfienest/``。

    迁移规则：
    1. ``~/.elfienest/`` 已存在 → 返回 True（已迁移）
    2. 旧 ``data/`` 存在 → 复制内容到 ``~/.elfienest/``
    3. 旧 ``runtime/runtime_config.json`` 存在 → 转换为 YAML
    4. 两者都不存在 → 创建空目录结构
    5. 在旧 ``data/`` 中创建 ``.migrated`` 标记（不删除旧数据）

    Returns:
        True 表示迁移成功或已迁移
    """
    home = get_elfie_home()

    # 1. 已迁移：~/.elfienest/ 已存在且有内容
    if home.exists() and any(home.iterdir()):
        logger.info("数据目录已存在: %s，跳过迁移", home)
        return True

    migrated = False

    # 2. 迁移旧 data/ 目录
    if _OLD_DATA_DIR.exists() and any(_OLD_DATA_DIR.iterdir()):
        logger.info("检测到旧数据目录: %s，开始迁移...", _OLD_DATA_DIR)
        _copy_old_data_dir(_OLD_DATA_DIR, home)
        migrated = True

    # 3. 迁移旧 runtime_config.json → config.yaml
    if _OLD_RUNTIME_CONFIG.exists():
        logger.info("检测到旧配置文件: %s，转换为 YAML...", _OLD_RUNTIME_CONFIG)
        _convert_runtime_config_json(home)
        migrated = True

    # 4. 如果没有旧数据，创建空目录结构 + 默认 config.yaml
    if not migrated:
        logger.info("未检测到旧数据，创建空目录结构: %s", home)

    ensure_elfie_home()

    # 确保有 config.yaml（无旧数据时创建默认配置）
    config_yaml = get_config_path()
    if not config_yaml.exists():
        default_config = {"config_version": CURRENT_CONFIG_VERSION}
        config_yaml.parent.mkdir(parents=True, exist_ok=True)
        with open(config_yaml, "w", encoding="utf-8") as f:
            yaml.dump(default_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        logger.info("已创建默认配置文件: %s", config_yaml)

    # 5. 在旧 data/ 目录中创建 .migrated 标记
    if _OLD_DATA_DIR.exists():
        marker = _OLD_DATA_DIR / ".migrated"
        if not marker.exists():
            marker.write_text("migrated", encoding="utf-8")
            logger.info("已在旧数据目录创建 .migrated 标记: %s", marker)

    logger.info("数据目录迁移完成: %s", home)
    return True


def _copy_old_data_dir(source_dir: Path, home: Path) -> None:
    """将旧数据目录内容复制到 ~/.elfienest/。

    映射关系：
    - source/nest.db → ~/.elfienest/nest.db
    - source/elfies/ → ~/.elfienest/elfies/
    - source/.elfie_memories.json → ~/.elfienest/.elfie_memories.json
    - source/graph_memory.db → ~/.elfienest/graph_memory.db（如存在）
    """
    home.mkdir(parents=True, exist_ok=True)

    # nest.db
    old_db = source_dir / "nest.db"
    if old_db.exists():
        shutil.copy2(str(old_db), str(home / "nest.db"))
        logger.info("已迁移: nest.db")

    # elfies/
    old_elfies = source_dir / "elfies"
    if old_elfies.exists() and old_elfies.is_dir():
        new_elfies = home / "elfies"
        if new_elfies.exists():
            shutil.rmtree(str(new_elfies))
        shutil.copytree(str(old_elfies), str(new_elfies))
        logger.info("已迁移: elfies/")

    # .elfie_memories.json
    old_memories = source_dir / ".elfie_memories.json"
    if old_memories.exists():
        shutil.copy2(str(old_memories), str(home / ".elfie_memories.json"))
        logger.info("已迁移: .elfie_memories.json")

    # graph_memory.db
    old_graph = source_dir / "graph_memory.db"
    if old_graph.exists():
        shutil.copy2(str(old_graph), str(home / "graph_memory.db"))
        logger.info("已迁移: graph_memory.db")


def _convert_runtime_config_json(home: Path) -> None:
    """将旧 runtime/runtime_config.json 转换为 ~/.elfienest/config.yaml。

    如果 config.yaml 已存在则跳过（不覆盖）。
    """
    config_yaml = home / "config.yaml"
    if config_yaml.exists():
        logger.info("config.yaml 已存在，跳过 JSON 转换")
        return

    try:
        with open(_OLD_RUNTIME_CONFIG, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("读取旧配置文件失败: %s", e)
        return

    # 确保有 config_version
    data.setdefault("config_version", 1)

    home.mkdir(parents=True, exist_ok=True)
    with open(config_yaml, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    logger.info("已将 runtime_config.json 转换为 config.yaml: %s", config_yaml)


# ---------------------------------------------------------------------------
# 版本化配置迁移
# ---------------------------------------------------------------------------


def migrate_config(config_version: Optional[int] = None) -> None:
    """版本化配置迁移：按版本号顺序应用迁移函数。

    参考 Hermes migrate_config 模式：
    1. 从 config.yaml 读取 config_version（默认 1）
    2. 按版本号顺序应用迁移函数
    3. 将更新后的 config_version 写回 config.yaml

    Args:
        config_version: 强制指定起始版本号（用于测试），默认从文件读取

    也可传入 dict 直接进行内存迁移（用于测试）::

        result = migrate_config({"config_version": 1, "providers": {}})
        assert result["config_version"] == CURRENT_CONFIG_VERSION
    """
    if isinstance(config_version, dict):
        return _migrate_config_dict(config_version)

    config_path = get_config_path()

    if not config_path.exists():
        logger.info("config.yaml 不存在，跳过配置迁移")
        return

    try:
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except (yaml.YAMLError, OSError) as e:
        logger.warning("读取 config.yaml 失败: %s", e)
        return

    current_version = config_version if config_version is not None else config.get("config_version", 1)

    # 按版本号顺序应用迁移
    max_registered = max(_CONFIG_MIGRATIONS.keys()) if _CONFIG_MIGRATIONS else 0
    for version in range(current_version + 1, max_registered + 1):
        migration_func = _CONFIG_MIGRATIONS.get(version)
        if migration_func is None:
            continue
        logger.info("应用配置迁移: v%d → v%d", version - 1, version)
        config = migration_func(config)
        config["config_version"] = version

    # 写回
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    logger.info("配置迁移完成，当前版本: %d", config.get("config_version", 1))


def get_config_version() -> int:
    """读取当前配置版本号。

    Returns:
        配置版本号，config.yaml 不存在时返回 0
    """
    config_path = get_config_path()
    if not config_path.exists():
        return 0

    try:
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        return int(config.get("config_version", 1))
    except (yaml.YAMLError, OSError, ValueError, TypeError):
        return 1


def _migrate_config_dict(config: Dict[str, Any]) -> Dict[str, Any]:
    """对内存中的配置字典应用版本迁移（不读写文件）。"""
    current_version = config.get("config_version", 1)
    max_registered = max(_CONFIG_MIGRATIONS.keys()) if _CONFIG_MIGRATIONS else 0
    for version in range(current_version + 1, max_registered + 1):
        migration_func = _CONFIG_MIGRATIONS.get(version)
        if migration_func is None:
            continue
        config = migration_func(config)
        config["config_version"] = version
    return config


_migrate_old_data_dir = _copy_old_data_dir
_migrate_runtime_config_json = _convert_runtime_config_json
