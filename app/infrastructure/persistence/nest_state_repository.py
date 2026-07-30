"""Final database adapter for orchestration-owned semantic Nest state."""

from __future__ import annotations

import sqlite3
from typing import Final

from app.infrastructure.persistence.nest_repository import (
    DEFAULT_NEST_ID,
    SQLiteNestRepository,
)
from app.infrastructure.persistence.store import get_db
from nest.state.models import PersistentResidentState, ResidentPresence, WorldCatalog
from nest.state.repository import NestPersistenceError, NestPersistenceSnapshot

_PRESENCE_TO_STATUS: Final = {
    ResidentPresence.ACTIVE: "online",
    ResidentPresence.AWAY: "away",
    ResidentPresence.PENDING_RUNTIME: "offline",
}
_STATUS_TO_PRESENCE: Final = {
    "online": ResidentPresence.ACTIVE,
    "away": ResidentPresence.AWAY,
    "offline": ResidentPresence.PENDING_RUNTIME,
}


class SQLiteNestStateRepository:
    """Persist settings and resident semantics without Godot geometry or catalogs."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def load_snapshot(self) -> NestPersistenceSnapshot:
        """Restore final settings and Elfie presence; Runtime supplies its catalog."""
        try:
            with get_db(self._db_path) as connection:
                SQLiteNestRepository(connection).ensure_default_config()
                config = connection.execute(
                    """SELECT bed_count, clock_anchor_seconds
                       FROM nest_settings WHERE nest_id=?""",
                    (DEFAULT_NEST_ID,),
                ).fetchone()
                rows = connection.execute(
                    "SELECT elfie_id, status FROM elfies ORDER BY elfie_id"
                ).fetchall()
                connection.commit()
        except sqlite3.Error as error:
            raise NestPersistenceError(str(error)) from error
        return NestPersistenceSnapshot(
            desired_bed_count=int(config["bed_count"]),
            elapsed_seconds=float(config["clock_anchor_seconds"]),
            catalog=None,
            residents=tuple(
                PersistentResidentState(
                    elfie_id=str(row["elfie_id"]),
                    presence=_STATUS_TO_PRESENCE[str(row["status"])],
                )
                for row in rows
            ),
        )

    def save_catalog(self, catalog: WorldCatalog) -> None:
        """Save only the applied revision; Runtime remains catalog authority."""
        if catalog.nest_id != DEFAULT_NEST_ID:
            raise NestPersistenceError(f"unsupported nest_id: {catalog.nest_id}")
        try:
            with get_db(self._db_path) as connection:
                SQLiteNestRepository(connection).ensure_default_config()
                connection.execute(
                    """UPDATE nest_settings SET applied_world_revision=?,
                       updated_at=CURRENT_TIMESTAMP WHERE nest_id=?""",
                    (catalog.revision, DEFAULT_NEST_ID),
                )
                connection.commit()
        except sqlite3.Error as error:
            raise NestPersistenceError(str(error)) from error

    def save_resident(self, resident: PersistentResidentState) -> None:
        """Persist only the resident presence; home anchors remain Runtime facts."""
        try:
            with get_db(self._db_path) as connection:
                cursor = connection.execute(
                    """UPDATE elfies SET status=?, updated_at=CURRENT_TIMESTAMP
                       WHERE elfie_id=?""",
                    (_PRESENCE_TO_STATUS[resident.presence], resident.elfie_id),
                )
                if cursor.rowcount != 1:
                    raise NestPersistenceError(f"elfie not found: {resident.elfie_id}")
                connection.commit()
        except sqlite3.Error as error:
            raise NestPersistenceError(str(error)) from error

    def remove_resident(self, elfie_id: str) -> None:
        """Make a resident offline and unassigned without deleting its Elfie row."""
        try:
            with get_db(self._db_path) as connection:
                cursor = connection.execute(
                    """UPDATE elfies SET status='offline', bed_number=NULL,
                       updated_at=CURRENT_TIMESTAMP WHERE elfie_id=?""",
                    (elfie_id,),
                )
                if cursor.rowcount != 1:
                    raise NestPersistenceError(f"elfie not found: {elfie_id}")
                connection.commit()
        except sqlite3.Error as error:
            raise NestPersistenceError(str(error)) from error


__all__ = ("SQLiteNestStateRepository",)
