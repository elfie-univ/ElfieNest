"""SQLite implementation of the Nest Management persistence Port."""

from __future__ import annotations

import sqlite3
from typing import Final

from app.features.nest_management import (
    NestBedRecord,
    NestPortBedNotFound,
    NestPortConflict,
    NestPortError,
    NestPortResidentNotFound,
    NestSnapshotRecord,
)
from infrastructure.persistence.nest_db.sqlite_connection import app_sqlite_connection
from nest.public import AnchorKind, NestConfig, WorldCatalog

DEFAULT_TICK_INTERVAL_SECONDS: Final = 1.0


class SQLiteNestManagementAdapter:
    """Persist Nest settings and stable Home anchor assignments."""

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

    def initialize_bed_count(self, bed_count: int) -> NestSnapshotRecord:
        """Create Setup's one authoritative Nest row, then apply its chosen size."""
        configured = NestConfig(bed_count=bed_count)
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """INSERT OR IGNORE INTO nest_settings
                       (nest_id,bed_count,tick_interval_sec) VALUES (?,?,?)""",
                    (
                        configured.nest_id,
                        configured.bed_count,
                        DEFAULT_TICK_INTERVAL_SECONDS,
                    ),
                )
                connection.execute(
                    """UPDATE nest_settings SET bed_count=?,updated_at=CURRENT_TIMESTAMP
                       WHERE nest_id=?""",
                    (configured.bed_count, configured.nest_id),
                )
                snapshot = self._load_snapshot(connection)
                connection.commit()
                return snapshot
        except sqlite3.IntegrityError as error:
            raise NestPortConflict("bed_count conflicts with assignments") from error
        except sqlite3.Error as error:
            raise NestPortError("unable to initialize Nest configuration") from error

    def assign_home(self, elfie_id: str, home_anchor_id: str | None) -> None:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                if home_anchor_id is not None:
                    catalog = self._load_catalog(connection)
                    if catalog is None or not _is_active_bed(catalog, home_anchor_id):
                        raise NestPortBedNotFound("home anchor not found")
                cursor = connection.execute(
                    """UPDATE elfies
                       SET home_anchor_id=?, updated_at=CURRENT_TIMESTAMP
                       WHERE elfie_id=?""",
                    (home_anchor_id, elfie_id),
                )
                if cursor.rowcount != 1:
                    raise NestPortResidentNotFound("Elfie not found")
                connection.commit()
        except (NestPortBedNotFound, NestPortResidentNotFound):
            raise
        except sqlite3.IntegrityError as error:
            raise NestPortConflict("bed already occupied") from error
        except sqlite3.Error as error:
            raise NestPortError("unable to assign Nest home") from error

    @staticmethod
    def _load_snapshot(connection: sqlite3.Connection) -> NestSnapshotRecord:
        defaults = NestConfig()
        configuration = connection.execute(
            """SELECT bed_count, applied_world_revision, world_catalog_json
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
        catalog = SQLiteNestManagementAdapter._load_catalog(connection)
        occupants = {
            str(row["home_anchor_id"]): row
            for row in connection.execute(
                """SELECT e.elfie_id, e.name, e.owner_user_id, e.species,
                          e.home_anchor_id, u.account_id, u.display_name
                   FROM elfies e JOIN users u ON u.id=e.owner_user_id
                   WHERE e.home_anchor_id IS NOT NULL"""
            ).fetchall()
        }
        beds = () if catalog is None else tuple(
            SQLiteNestManagementAdapter._bed_record(
                anchor_id=anchor.anchor_id,
                label=anchor.label,
                order=index,
                occupant=occupants.get(anchor.anchor_id),
            )
            for index, anchor in enumerate(_ordered_bed_anchors(catalog))
        )
        return NestSnapshotRecord(
            desired_bed_count=desired_bed_count,
            applied_world_revision=applied_world_revision,
            beds=beds,
        )

    @staticmethod
    def _bed_record(
        *,
        anchor_id: str,
        label: str,
        order: int,
        occupant: sqlite3.Row | None,
    ) -> NestBedRecord:
        return NestBedRecord(
            anchor_id=anchor_id,
            label=label,
            order=order,
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

    @staticmethod
    def _load_catalog(connection: sqlite3.Connection) -> WorldCatalog | None:
        row = connection.execute(
            "SELECT world_catalog_json FROM nest_settings WHERE nest_id=?",
            (NestConfig().nest_id,),
        ).fetchone()
        if row is None or row["world_catalog_json"] is None:
            return None
        try:
            return WorldCatalog.model_validate_json(row["world_catalog_json"])
        except ValueError as error:
            raise NestPortError("stored Nest world catalog is invalid") from error


def _ordered_bed_anchors(catalog: WorldCatalog) -> tuple:
    return tuple(
        anchor
        for zone in sorted(catalog.zones, key=lambda item: (item.order, item.zone_id))
        for anchor in sorted(zone.anchors, key=lambda item: (item.order, item.anchor_id))
        if anchor.kind is AnchorKind.BED and anchor.active
    )


def _is_active_bed(catalog: WorldCatalog, anchor_id: str) -> bool:
    return any(anchor.anchor_id == anchor_id for anchor in _ordered_bed_anchors(catalog))


__all__ = ("DEFAULT_TICK_INTERVAL_SECONDS", "SQLiteNestManagementAdapter")
