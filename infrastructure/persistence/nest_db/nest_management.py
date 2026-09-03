"""Read-only SQLite projection for Nest Management."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import yaml

from app.features.nest_management import (
    NestBedRecord,
    NestPortError,
    NestSnapshotRecord,
)
from infrastructure.persistence.elfie_workspace.identity import load_profile_from_db
from infrastructure.persistence.nest_db.sqlite_connection import app_sqlite_connection
from nest.public import AnchorKind, NestConfig, WorldCatalog


class SQLiteNestManagementAdapter:
    """Read Nest settings and stable Home assignments without mutating them."""

    def __init__(self, db_path: str, *, nest_config: NestConfig | None = None) -> None:
        self._db_path = db_path
        self._nest_config = nest_config or NestConfig()

    def load_snapshot(self) -> NestSnapshotRecord:
        """Read the current projection without creating or repairing product state."""
        try:
            with app_sqlite_connection(self._db_path) as connection:
                return self._load_snapshot(connection)
        except sqlite3.Error as error:
            raise NestPortError("unable to read Nest management state") from error

    def _load_snapshot(self, connection: sqlite3.Connection) -> NestSnapshotRecord:
        defaults = self._nest_config
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
        catalog = self._load_catalog(connection)
        occupants = self._load_occupants(connection)
        beds = (
            ()
            if catalog is None
            else tuple(
                SQLiteNestManagementAdapter._bed_record(
                    anchor_id=anchor.anchor_id,
                    label=anchor.label,
                    order=index,
                    occupant=occupants.get(anchor.anchor_id),
                )
                for index, anchor in enumerate(_ordered_bed_anchors(catalog))
            )
        )
        return NestSnapshotRecord(
            desired_bed_count=desired_bed_count,
            applied_world_revision=applied_world_revision,
            beds=beds,
        )

    def _load_occupants(
        self, connection: sqlite3.Connection
    ) -> dict[str, _OccupantProjection]:
        rows = connection.execute(
            """SELECT e.elfie_id, e.owner_user_id, e.home_anchor_id,
                      u.account_id, u.display_name
               FROM elfies AS e JOIN users AS u ON u.id=e.owner_user_id
               WHERE e.home_anchor_id IS NOT NULL"""
        ).fetchall()
        occupants: dict[str, _OccupantProjection] = {}
        for row in rows:
            elfie_id = str(row["elfie_id"])
            try:
                profile = load_profile_from_db(self._db_path, elfie_id)
            except (OSError, TypeError, ValueError, yaml.YAMLError) as error:
                raise NestPortError("committed Elfie Profile is unavailable") from error
            occupants[str(row["home_anchor_id"])] = _OccupantProjection(
                elfie_id=elfie_id,
                name=profile.identity.display_name,
                owner_user_id=int(row["owner_user_id"]),
                species_id=profile.identity.species_id,
                owner_account_id=str(row["account_id"]),
                owner_display_name=(
                    None if row["display_name"] is None else str(row["display_name"])
                ),
            )
        return occupants

    @staticmethod
    def _bed_record(
        *,
        anchor_id: str,
        label: str,
        order: int,
        occupant: _OccupantProjection | None,
    ) -> NestBedRecord:
        return NestBedRecord(
            anchor_id=anchor_id,
            label=label,
            order=order,
            occupant_id=None if occupant is None else occupant.elfie_id,
            occupant_name=None if occupant is None else occupant.name,
            occupant_owner_user_id=(
                None if occupant is None else occupant.owner_user_id
            ),
            occupant_species_id=(None if occupant is None else occupant.species_id),
            occupant_owner_account_id=(
                None if occupant is None else occupant.owner_account_id
            ),
            occupant_owner_display_name=(
                None if occupant is None else occupant.owner_display_name
            ),
        )

    def _load_catalog(self, connection: sqlite3.Connection) -> WorldCatalog | None:
        row = connection.execute(
            "SELECT world_catalog_json FROM nest_settings WHERE nest_id=?",
            (self._nest_config.nest_id,),
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
        for anchor in sorted(
            zone.anchors, key=lambda item: (item.order, item.anchor_id)
        )
        if anchor.kind is AnchorKind.BED and anchor.active
    )


@dataclass(frozen=True)
class _OccupantProjection:
    elfie_id: str
    name: str
    owner_user_id: int
    species_id: str
    owner_account_id: str
    owner_display_name: str | None


__all__ = ("SQLiteNestManagementAdapter",)
