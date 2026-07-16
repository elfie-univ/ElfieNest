"""显式的一次性生产数据迁移命令。"""

from __future__ import annotations

from runtime.storage.migration import MigrationError, migrate_data_home


def run_migrate() -> int:
    """迁移旧 data/runtime_config.json，返回可脚本判断的退出码。"""
    try:
        migrate_data_home()
    except (MigrationError, OSError) as exc:
        print(f"迁移失败: {exc}")
        return 1
    print("迁移完成（没有旧数据时为空迁移）。")
    return 0
