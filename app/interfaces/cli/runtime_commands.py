from __future__ import annotations

import sys
from importlib import metadata
from pathlib import Path

from app.features.operations import (
    BackupDatabasesCommand,
    GetUsageStatsQuery,
    ListTableCountsQuery,
    OperationsError,
    OperationsFacade,
    ResetDatabasesCommand,
)
from app.interfaces.cli.packaged_runtime import packaged_application_version
from app.orchestration.lifecycle import LifecycleFacade

PACKAGE_NAME = "elfienest"


def show_status(operations: OperationsFacade, lifecycle: LifecycleFacade) -> None:
    print("  📊 Service Status")
    print("  " + "=" * 45)
    print()

    for port_status in lifecycle.default_port_statuses():
        if port_status.running:
            print(f"  ✅ {port_status.name}: running (port {port_status.port})")
        else:
            print(f"  ⭕ {port_status.name}: not running (port {port_status.port})")

    print()
    try:
        stats = operations.get_usage_stats(GetUsageStatsQuery())
        print(f"  📦 Database: {stats.user_count} users, {stats.elfie_count} elfies")
    except OperationsError:
        print("  ❌ Database not initialized")

    print()


def dispatch_db(operations: OperationsFacade, subcmd: str | None) -> None:
    print("  🗄️  Database Tools")
    print("  " + "=" * 45)
    print()

    if subcmd == "backup":
        backup_db(operations)
    elif subcmd == "reset":
        reset_db(operations)
    else:
        show_db(operations)

    print()


def backup_db(operations: OperationsFacade) -> None:
    try:
        result = operations.backup_databases(BackupDatabasesCommand())
    except OperationsError as e:
        print(f"  ❌ Backup failed: {e}")
        return
    print(f"  ✅ Databases backed up to: {result.backup_path}")


def reset_db(operations: OperationsFacade) -> None:
    print("  ⚠️  This will reset Nest, chat, and memory databases. Continue?")
    choice = input("Type 'yes' to confirm: ").strip()
    if choice.lower() != "yes":
        return
    try:
        operations.reset_databases(ResetDatabasesCommand())
    except OperationsError as e:
        print(f"  ❌ Delete failed: {e}")
        return
    print("  ✅ Databases deleted; restart service to create fresh databases")


def show_db(operations: OperationsFacade) -> None:
    print("  Available commands:")
    print("    elfienest db backup  - Backup all databases")
    print("    elfienest db reset   - Reset all databases")
    print()

    try:
        table_counts = operations.list_table_counts(ListTableCountsQuery()).items
    except OperationsError as e:
        print(f"  ❌ Cannot read database: {e}")
        return

    print("  【Database Tables】")
    for table_count in table_counts:
        print(f"    • {table_count.name}: {table_count.count} records")


def show_version() -> None:
    print(f"  ElfieNest v{_current_version()}")
    print()
    print("  🦊 Embodied AI Creature System")
    print("  An AI creature simulation system based on three-layer brain architecture")
    print()


def _current_version() -> str:
    """Return the installed package version used by this launcher."""
    try:
        return metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return packaged_application_version(Path(sys.executable)) or "unknown"
