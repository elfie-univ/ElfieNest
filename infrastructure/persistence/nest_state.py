"""SQLite adapter for orchestration-owned semantic Nest state."""

from __future__ import annotations

import sqlite3
from typing import Final

from nest import NestConfig
from nest.state.models import PersistentResidentState, ResidentPresence, WorldCatalog
from nest.state.repository import NestPersistenceError, NestPersistenceSnapshot

from .sqlite_connection import app_sqlite_connection

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
_BEDS_PER_DORM: Final = 4


class SQLiteNestStateAdapter:
    """Persist Nest runtime revision and resident semantics in the final database."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def load_snapshot(self) -> NestPersistenceSnapshot:
        """Restore state without creating or repairing product configuration."""
        defaults = NestConfig()
        try:
            with app_sqlite_connection(self._db_path) as connection:
                config = connection.execute(
                    """SELECT bed_count, clock_anchor_seconds
                       FROM nest_settings WHERE nest_id=?""",
                    (defaults.nest_id,),
                ).fetchone()
                rows = connection.execute(
                    "SELECT elfie_id, status FROM elfies ORDER BY elfie_id"
                ).fetchall()
        except sqlite3.Error as error:
            raise NestPersistenceError(str(error)) from error
        return NestPersistenceSnapshot(
            desired_bed_count=(
                defaults.bed_count if config is None else int(config["bed_count"])
            ),
            elapsed_seconds=(
                0.0 if config is None else float(config["clock_anchor_seconds"])
            ),
            catalog=None,
            residents=tuple(
                PersistentResidentState(
                    elfie_id=str(row["elfie_id"]),
                    presence=_STATUS_TO_PRESENCE[str(row["status"])],
                )
                for row in rows
            ),
        )

    def load_home_assignments(self) -> dict[str, PersistentResidentState]:
        """Read persisted bed choices as semantic Runtime home assignments."""
        try:
            with app_sqlite_connection(self._db_path) as connection:
                rows = connection.execute(
                    """SELECT elfie_id, status, bed_number FROM elfies
                       WHERE bed_number IS NOT NULL ORDER BY elfie_id"""
                ).fetchall()
        except sqlite3.Error as error:
            raise NestPersistenceError(str(error)) from error
        return {
            str(row["elfie_id"]): _persisted_home_state(
                elfie_id=str(row["elfie_id"]),
                status=str(row["status"]),
                bed_number=int(row["bed_number"]),
            )
            for row in rows
        }

    def save_catalog(self, catalog: WorldCatalog) -> None:
        """Save only the applied revision; Runtime remains catalog authority."""
        nest_id = NestConfig().nest_id
        if catalog.nest_id != nest_id:
            raise NestPersistenceError(f"unsupported nest_id: {catalog.nest_id}")
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """UPDATE nest_settings SET applied_world_revision=?,
                       updated_at=CURRENT_TIMESTAMP WHERE nest_id=?""",
                    (catalog.revision, nest_id),
                )
                if cursor.rowcount != 1:
                    raise NestPersistenceError("Nest configuration not found")
                connection.commit()
        except sqlite3.Error as error:
            raise NestPersistenceError(str(error)) from error

    def save_resident(self, resident: PersistentResidentState) -> None:
        """Persist only resident presence; Runtime remains home-anchor authority."""
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
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
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
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


def _persisted_home_state(
    *, elfie_id: str, status: str, bed_number: int
) -> PersistentResidentState:
    if bed_number < 1:
        raise NestPersistenceError(f"invalid persisted bed number: {bed_number}")
    dorm_index, bed_index = divmod(bed_number - 1, _BEDS_PER_DORM)
    zone_id = f"dorm-{dorm_index + 1:02d}"
    return PersistentResidentState(
        elfie_id=elfie_id,
        presence=_STATUS_TO_PRESENCE[status],
        home_zone_id=zone_id,
        home_anchor_id=f"{zone_id}/bed-{bed_index + 1:02d}",
    )


__all__ = ("SQLiteNestStateAdapter",)
