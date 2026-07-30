"""Maintenance operations for all databases in one final product root."""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Final

from ai_runtime.storage.data_home import data_home_from_db_path
from ai_runtime.storage.data_layout import final_root_layout

_ELFIE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9]{8}$")


def backup_final_databases(database_path: Path, timestamp: datetime) -> Path:
    """Create one consistent sibling backup tree for every final SQLite store."""
    data_home = data_home_from_db_path(database_path)
    backup_root = data_home.with_name(
        f"{data_home.name}.database-backup.{timestamp.strftime('%Y%m%d_%H%M%S_%f')}"
    )
    backup_root.mkdir(mode=0o700, parents=False, exist_ok=False)
    if os.name != "nt":
        os.chmod(backup_root, 0o700)
    for source in final_database_paths(database_path):
        relative = source.relative_to(data_home)
        target = backup_root / relative
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with sqlite3.connect(source) as source_connection:
            with sqlite3.connect(target) as target_connection:
                source_connection.backup(target_connection)
        if os.name != "nt":
            os.chmod(target.parent, 0o700)
            os.chmod(target, 0o600)
    return backup_root


def reset_final_databases(database_path: Path) -> None:
    """Remove the root, history, and knowledge databases but keep other data."""
    for path in final_database_paths(database_path):
        path.unlink()
        for suffix in ("-shm", "-wal"):
            sidecar = path.with_name(f"{path.name}{suffix}")
            if sidecar.exists():
                sidecar.unlink()


def final_database_paths(database_path: Path) -> tuple[Path, ...]:
    """Enumerate only final database locations without following Elfie symlinks."""
    data_home = data_home_from_db_path(database_path)
    layout = final_root_layout(data_home)
    paths = [layout.nest_database]
    elfies_root = data_home / "elfies"
    if elfies_root.is_dir() and not elfies_root.is_symlink():
        for workspace in sorted(elfies_root.iterdir()):
            if workspace.is_symlink() or not workspace.is_dir():
                continue
            if _ELFIE_ID_PATTERN.fullmatch(workspace.name) is None:
                continue
            elfie_layout = layout.elfie(workspace.name)
            paths.extend(
                (elfie_layout.history_database, elfie_layout.knowledge_database)
            )
    return tuple(path for path in paths if path.is_file() and not path.is_symlink())
