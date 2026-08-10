from __future__ import annotations

import os
import sys
from importlib import metadata
from pathlib import Path

from app.features.administration.system_service import (
    default_port_statuses,
)
from app.features.operations import (
    BackupDatabasesCommand,
    GetUsageStatsQuery,
    ListActiveSessionsQuery,
    ListTableCountsQuery,
    OperationsError,
    OperationsFacade,
    ResetDatabasesCommand,
)
from app.interfaces.cli.packaged_runtime import packaged_application_version

PACKAGE_NAME = "elfienest"


def show_status(operations: OperationsFacade) -> None:
    print("  📊 Service Status")
    print("  " + "=" * 45)
    print()

    for port_status in default_port_statuses():
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


def show_stats(operations: OperationsFacade) -> None:
    print("  📈 Usage Statistics")
    print("  " + "=" * 45)
    print()

    try:
        stats = operations.get_usage_stats(GetUsageStatsQuery())
    except OperationsError as e:
        print(f"  ❌ Cannot read statistics: {e}")
        print()
        return

    print("  【User Statistics】")
    print(f"    Total users: {stats.user_count}")
    print(f"    Owners: {stats.owner_count}")
    print(f"    Regular users: {stats.user_count - stats.owner_count}")
    print()

    print("  【Elfie Statistics】")
    print(f"    Total elfies: {stats.elfie_count}")
    for row in stats.species_stats:
        print(f"    {row.species_id}: {row.count}")
    print()

    print("  【Session Statistics】")
    print(f"    Active sessions: {stats.session_count}")
    print()


def show_sessions(operations: OperationsFacade) -> None:
    print("  👥 Session Management")
    print("  " + "=" * 45)
    print()

    try:
        sessions = operations.list_active_sessions(ListActiveSessionsQuery()).items
    except OperationsError as e:
        print(f"  ❌ Cannot read sessions: {e}")
        print()
        return

    if sessions:
        print("  【Online Accounts】")
        for session in sessions:
            token_short = session.token_hash[:8] + "..."
            print(
                f"    • {session.account_id} "
                f"(token: {token_short}, expires: {session.expires_at})"
            )
    else:
        print("  No active sessions")

    print()


def show_logs() -> None:
    print("  📝 Log Viewer")
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
                print("    Cannot read")
            else:
                for line in lines:
                    print(f"    {line.rstrip()}")
            print()

    print("  💡 View full logs: tail -100 /tmp/serve.log")
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
