"""SQLite projections and database maintenance for Operations."""

from __future__ import annotations

import os
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, Tuple

import yaml

from app.features.operations import (
    OperationsPortDatabaseMissing,
    OperationsPortError,
    OperationsPortUnsafeTarget,
    StoredActiveSession,
    StoredDatabaseBackup,
    StoredSpeciesCount,
    StoredTableCount,
    StoredUsageStats,
)
from infrastructure.persistence.elfie_workspace.identity import load_profile_from_db
from infrastructure.persistence.layout.data_home import data_home_from_db_path
from infrastructure.persistence.layout.data_layout import final_root_layout
from infrastructure.persistence.nest_db.sqlite_connection import app_sqlite_connection

_ELFIE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9]{8}$")


class SQLiteOperationsAdapter:
    """Read management projections and maintain the selected final data root."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def collect_usage_stats(self) -> StoredUsageStats:
        database_path = self._require_database()
        now = datetime.now(timezone.utc).isoformat()
        try:
            with app_sqlite_connection(database_path) as connection:
                user_count = self._count(connection, "users")
                owner_row = connection.execute(
                    "SELECT COUNT(*) FROM users WHERE role='owner'"
                ).fetchone()
                owner_count = 0 if owner_row is None else int(owner_row[0])
                elfie_count = self._count(connection, "elfies")
                session_row = connection.execute(
                    """SELECT COUNT(*) FROM sessions
                       WHERE revoked_at IS NULL AND expires_at>?""",
                    (now,),
                ).fetchone()
                session_count = 0 if session_row is None else int(session_row[0])
                species_counts: Counter[str] = Counter()
                resident_rows = connection.execute(
                    "SELECT elfie_id FROM elfies ORDER BY elfie_id"
                ).fetchall()
                for resident_row in resident_rows:
                    profile = load_profile_from_db(
                        database_path, str(resident_row["elfie_id"])
                    )
                    species_counts[profile.identity.species_id] += 1
                species_stats = tuple(
                    StoredSpeciesCount(species_id=species_id, count=count)
                    for species_id, count in sorted(species_counts.items())
                )
        except (OSError, TypeError, ValueError, yaml.YAMLError, sqlite3.Error) as error:
            raise OperationsPortError("unable to read system statistics") from error
        return StoredUsageStats(
            user_count=user_count,
            owner_count=owner_count,
            elfie_count=elfie_count,
            session_count=session_count,
            species_stats=species_stats,
        )

    def list_active_sessions(self, limit: int) -> Tuple[StoredActiveSession, ...]:
        database_path = self._require_database()
        now = datetime.now(timezone.utc).isoformat()
        try:
            with app_sqlite_connection(database_path) as connection:
                rows = connection.execute(
                    """SELECT sessions.token_hash,users.account_id,sessions.expires_at
                       FROM sessions JOIN users ON sessions.user_id=users.id
                       WHERE sessions.revoked_at IS NULL AND sessions.expires_at>?
                       ORDER BY sessions.expires_at DESC LIMIT ?""",
                    (now, limit),
                ).fetchall()
        except sqlite3.Error as error:
            raise OperationsPortError("unable to read active sessions") from error
        return tuple(
            StoredActiveSession(
                token_hash=str(row["token_hash"]),
                account_id=str(row["account_id"]),
                expires_at=str(row["expires_at"]),
            )
            for row in rows
        )

    def list_table_counts(self) -> Tuple[StoredTableCount, ...]:
        database_path = self._require_database()
        try:
            with app_sqlite_connection(database_path) as connection:
                names = tuple(
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                    ).fetchall()
                )
                counts = tuple(
                    StoredTableCount(
                        name=name,
                        count=self._count(connection, name),
                    )
                    for name in names
                )
        except sqlite3.Error as error:
            raise OperationsPortError("unable to read database table counts") from error
        return counts

    def backup_databases(self) -> StoredDatabaseBackup:
        database_path = self._require_database()
        try:
            backup_path = self._backup_final_databases(
                database_path,
                datetime.now(),
            )
        except (OSError, sqlite3.Error) as error:
            raise OperationsPortError("unable to back up databases") from error
        return StoredDatabaseBackup(backup_path=backup_path)

    def reset_databases(self) -> None:
        database_path = self._require_database()
        self._validate_reset_target(database_path)
        try:
            for path in self._final_database_paths(database_path):
                path.unlink()
                for suffix in ("-shm", "-wal"):
                    sidecar = path.with_name(f"{path.name}{suffix}")
                    if sidecar.exists():
                        sidecar.unlink()
        except OSError as error:
            raise OperationsPortError("unable to reset databases") from error

    def _require_database(self) -> Path:
        database_path = Path(self._db_path)
        if not database_path.exists():
            raise OperationsPortDatabaseMissing(f"数据库不存在: {database_path}")
        return database_path

    @staticmethod
    def _count(connection: sqlite3.Connection, table_name: str) -> int:
        quoted = '"' + table_name.replace('"', '""') + '"'
        row = connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()
        return 0 if row is None else int(row[0])

    @staticmethod
    def _validate_reset_target(database_path: Path) -> Path:
        data_home: Path = data_home_from_db_path(database_path)
        project_root = Path(__file__).resolve().parents[2]
        forbidden = {
            Path("/"),
            Path.home().resolve(),
            (Path.home() / ".elfienest").resolve(),
            project_root,
            Path("/tmp").resolve(),
            Path("/private/tmp").resolve(),
        }
        if data_home in forbidden:
            raise OperationsPortUnsafeTarget(
                f"refusing destructive reset for broad or default data root: {data_home}"
            )
        return data_home

    @classmethod
    def _backup_final_databases(
        cls,
        database_path: Path,
        timestamp: datetime,
    ) -> Path:
        data_home: Path = data_home_from_db_path(database_path)
        backup_root = data_home.with_name(
            f"{data_home.name}.database-backup.{timestamp.strftime('%Y%m%d_%H%M%S_%f')}"
        )
        backup_root.mkdir(mode=0o700, parents=False, exist_ok=False)
        if os.name != "nt":
            os.chmod(backup_root, 0o700)
        for source in cls._final_database_paths(database_path):
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

    @staticmethod
    def _final_database_paths(database_path: Path) -> Tuple[Path, ...]:
        data_home: Path = data_home_from_db_path(database_path)
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


__all__ = ("SQLiteOperationsAdapter",)
