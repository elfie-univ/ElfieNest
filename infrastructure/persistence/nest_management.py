"""SQLite implementation of the Nest Management persistence Port."""

from __future__ import annotations

import sqlite3

from app.features.nest_management import (
    NestBedRecord,
    NestPortBedNotFound,
    NestPortConflict,
    NestPortError,
    NestPortResidentNotFound,
    NestSnapshotRecord,
)
from nest import NestConfig

from .sqlite_connection import app_sqlite_connection


class SQLiteNestManagementAdapter:
    """Persist only Nest settings and nullable Elfie bed numbers."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def load_snapshot(self) -> NestSnapshotRecord:
        """Read the current projection without creating or repairing product state."""
        try:
            with app_sqlite_connection(self._db_path) as connection:
                return self._load_snapshot(connection)
        except sqlite3.Error as error:
            raise NestPortError("unable to read Nest management state") from error

    def update_bed_count(self, bed_count: int) -> NestSnapshotRecord:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """UPDATE nest_settings
                       SET bed_count=?, updated_at=CURRENT_TIMESTAMP
                       WHERE nest_id=?""",
                    (bed_count, NestConfig().nest_id),
                )
                if cursor.rowcount != 1:
                    raise NestPortError("Nest configuration not found")
                snapshot = self._load_snapshot(connection)
                connection.commit()
                return snapshot
        except sqlite3.IntegrityError as error:
            raise NestPortConflict("bed_count conflicts with assignments") from error
        except sqlite3.Error as error:
            raise NestPortError("unable to update Nest configuration") from error

    def assign_bed(self, elfie_id: str, bed_number: int | None) -> None:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                if bed_number is not None:
                    configured = connection.execute(
                        "SELECT bed_count FROM nest_settings WHERE nest_id=?",
                        (NestConfig().nest_id,),
                    ).fetchone()
                    if configured is None:
                        raise NestPortError("Nest configuration not found")
                    if not 1 <= bed_number <= int(configured[0]):
                        raise NestPortBedNotFound("bed not found")
                cursor = connection.execute(
                    """UPDATE elfies
                       SET bed_number=?, updated_at=CURRENT_TIMESTAMP
                       WHERE elfie_id=?""",
                    (bed_number, elfie_id),
                )
                if cursor.rowcount != 1:
                    raise NestPortResidentNotFound("Elfie not found")
                connection.commit()
        except (NestPortBedNotFound, NestPortResidentNotFound):
            raise
        except sqlite3.IntegrityError as error:
            raise NestPortConflict("bed already occupied") from error
        except sqlite3.Error as error:
            raise NestPortError("unable to assign Nest bed") from error

    @staticmethod
    def _load_snapshot(connection: sqlite3.Connection) -> NestSnapshotRecord:
        defaults = NestConfig()
        configuration = connection.execute(
            """SELECT bed_count, applied_world_revision
               FROM nest_settings WHERE nest_id=?""",
            (defaults.nest_id,),
        ).fetchone()
        desired_bed_count = (
            defaults.bed_count
            if configuration is None
            else int(configuration["bed_count"])
        )
        applied_world_revision = (
            None
            if configuration is None or configuration["applied_world_revision"] is None
            else int(configuration["applied_world_revision"])
        )
        occupants = {
            int(row["bed_number"]): row
            for row in connection.execute(
                """SELECT e.elfie_id, e.name, e.owner_user_id, e.species,
                          e.bed_number, u.account_id, u.display_name
                   FROM elfies e JOIN users u ON u.id=e.owner_user_id
                   WHERE e.bed_number IS NOT NULL"""
            ).fetchall()
        }
        return NestSnapshotRecord(
            desired_bed_count=desired_bed_count,
            applied_world_revision=applied_world_revision,
            beds=tuple(
                SQLiteNestManagementAdapter._bed_record(number, occupants.get(number))
                for number in range(1, desired_bed_count + 1)
            ),
        )

    @staticmethod
    def _bed_record(
        number: int,
        occupant: sqlite3.Row | None,
    ) -> NestBedRecord:
        return NestBedRecord(
            bed_number=number,
            occupant_id=None if occupant is None else str(occupant["elfie_id"]),
            occupant_name=None if occupant is None else str(occupant["name"]),
            occupant_owner_user_id=(
                None if occupant is None else int(occupant["owner_user_id"])
            ),
            occupant_species_id=(
                None if occupant is None else str(occupant["species"])
            ),
            occupant_owner_account_id=(
                None if occupant is None else str(occupant["account_id"])
            ),
            occupant_owner_display_name=(
                None
                if occupant is None or occupant["display_name"] is None
                else str(occupant["display_name"])
            ),
        )


__all__ = ("SQLiteNestManagementAdapter",)
