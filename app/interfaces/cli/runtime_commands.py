from __future__ import annotations

import os
from importlib import metadata

from app.features.administration.system_service import (
    DatabaseUnavailableError,
    backup_database,
    collect_usage_stats,
    default_port_statuses,
    list_active_sessions,
    list_table_counts,
    reset_database,
)

PACKAGE_NAME = "elfienest"


def show_status() -> None:
    print("  📊 服务状态")
    print("  " + "=" * 45)
    print()

    for port_status in default_port_statuses():
        if port_status.running:
            print(f"  ✅ {port_status.name}: 运行中 (端口 {port_status.port})")
        else:
            print(f"  ⭕ {port_status.name}: 未运行 (端口 {port_status.port})")

    print()
    try:
        stats = collect_usage_stats()
        print(f"  📦 数据库: {stats.user_count} 用户, {stats.elfie_count} 精灵")
    except DatabaseUnavailableError:
        print("  ❌ 数据库未初始化")

    print()


def show_stats() -> None:
    print("  📈 使用统计")
    print("  " + "=" * 45)
    print()

    try:
        stats = collect_usage_stats()
    except DatabaseUnavailableError as e:
        print(f"  ❌ 无法读取统计: {e}")
        print()
        return

    print("  【用户统计】")
    print(f"    总用户数: {stats.user_count}")
    print(f"    Owner 数: {stats.owner_count}")
    print(f"    普通用户: {stats.user_count - stats.owner_count}")
    print()

    print("  【精灵统计】")
    print(f"    总精灵数: {stats.elfie_count}")
    for row in stats.species_stats:
        print(f"    {row.species_id}: {row.count}")
    print()

    print("  【会话统计】")
    print(f"    活跃会话: {stats.session_count}")
    print()


def show_sessions() -> None:
    print("  👥 会话管理")
    print("  " + "=" * 45)
    print()

    try:
        sessions = list_active_sessions()
    except DatabaseUnavailableError as e:
        print(f"  ❌ 无法读取会话: {e}")
        print()
        return

    if sessions:
        print("  【在线用户】")
        for session in sessions:
            token_short = session.token[:8] + "..."
            print(
                f"    • {session.username} "
                f"(token: {token_short}, 过期: {session.expires_at})"
            )
    else:
        print("  暂无活跃会话")

    print()


def show_logs() -> None:
    print("  📝 日志查看")
    print("  " + "=" * 45)
    print()

    log_files = [
        "/tmp/serve.log",
        "/tmp/serve_full.log",
        "/tmp/final_serve.log",
    ]

    for log_file in log_files:
        if os.path.exists(log_file):
            print(f"  【{log_file}】")
            try:
                with open(log_file) as file:
                    lines = file.readlines()[-20:]
            except OSError:
                print("    无法读取")
            else:
                for line in lines:
                    print(f"    {line.rstrip()}")
            print()

    print("  💡 查看完整日志: tail -100 /tmp/serve.log")
    print()


def dispatch_db(subcmd: str | None) -> None:
    print("  🗄️  数据库工具")
    print("  " + "=" * 45)
    print()

    if subcmd == "backup":
        backup_db()
    elif subcmd == "reset":
        reset_db()
    else:
        show_db()

    print()


def backup_db() -> None:
    try:
        backup_path = backup_database()
    except DatabaseUnavailableError as e:
        print(f"  ❌ 备份失败: {e}")
        return
    print(f"  ✅ 数据库已备份到: {backup_path}")


def reset_db() -> None:
    print("  ⚠️  这将删除所有数据，是否继续？")
    choice = input("输入 'yes' 确认: ").strip()
    if choice.lower() != "yes":
        return
    try:
        reset_database()
    except DatabaseUnavailableError as e:
        print(f"  ❌ 删除失败: {e}")
        return
    print("  ✅ 数据库已删除，重启服务将自动创建新数据库")


def show_db() -> None:
    print("  可用命令:")
    print("    elfienest db backup  - 备份数据库")
    print("    elfienest db reset   - 重置数据库")
    print()

    try:
        table_counts = list_table_counts()
    except DatabaseUnavailableError as e:
        print(f"  ❌ 无法读取数据库: {e}")
        return

    print("  【数据库表】")
    for table_count in table_counts:
        print(f"    • {table_count.name}: {table_count.count} 条记录")


def show_version() -> None:
    print(f"  ElfieNest v{_current_version()}")
    print()
    print("  🦊 仿生生命体系统")
    print("  一个基于三层大脑架构的 AI 生物模拟系统")
    print()


def _current_version() -> str:
    """Return the installed package version used by this launcher."""
    try:
        return metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return "unknown"
