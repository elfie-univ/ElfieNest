"""SQLite adapter for orchestration-owned semantic Nest state."""

from __future__ import annotations

import json
import sqlite3
from typing import Final

from infrastructure.persistence.nest_db.sqlite_connection import app_sqlite_connection
from nest.public import NestConfig
from nest.state.models import (
    AnchorKind,
    EnvironmentDesiredState,
    EnvironmentRule,
    PersistentResidentState,
    ResidentPresence,
    WorldCatalog,
)
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
                    """SELECT bed_count, clock_anchor_seconds, clock_paused,
                              time_scale, environment_desired_json, environment_rules_json,
                              world_catalog_json
                       FROM nest_settings WHERE nest_id=?""",
                    (defaults.nest_id,),
                ).fetchone()
                catalog = _catalog_from_row(config)
                rows = connection.execute(
                    "SELECT elfie_id, status, home_anchor_id FROM elfies ORDER BY elfie_id"
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
            catalog=catalog,
            clock_paused=(False if config is None else bool(config["clock_paused"])),
            time_scale=(1.0 if config is None else float(config["time_scale"])),
            environment_desired=_environment_desired_from_row(config),
            environment_rules=_environment_rules_from_row(config),
            residents=tuple(
                PersistentResidentState(
                    elfie_id=str(row["elfie_id"]),
                    presence=_STATUS_TO_PRESENCE[str(row["status"])],
                    home_zone_id=(
                        None
                        if row["home_anchor_id"] is None
                        else _zone_for_home_anchor(catalog, str(row["home_anchor_id"]))
                    ),
                    home_anchor_id=(
                        None
                        if row["home_anchor_id"] is None
                        else str(row["home_anchor_id"])
                    ),
                )
                for row in rows
            ),
        )

    def load_home_assignments(self) -> dict[str, PersistentResidentState]:
        """Read persisted bed choices as semantic Runtime home assignments."""
        try:
            with app_sqlite_connection(self._db_path) as connection:
                rows = connection.execute(
                    """SELECT elfie_id, status, home_anchor_id FROM elfies
                       WHERE home_anchor_id IS NOT NULL ORDER BY elfie_id"""
                ).fetchall()
                catalog_row = connection.execute(
                    "SELECT world_catalog_json FROM nest_settings WHERE nest_id=?",
                    (NestConfig().nest_id,),
                ).fetchone()
                catalog = _catalog_from_row(catalog_row)
        except sqlite3.Error as error:
            raise NestPersistenceError(str(error)) from error
        return {
            str(row["elfie_id"]): _persisted_home_state(
                elfie_id=str(row["elfie_id"]),
                status=str(row["status"]),
                home_anchor_id=str(row["home_anchor_id"]),
                catalog=catalog,
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
                       world_catalog_json=?,
                       updated_at=CURRENT_TIMESTAMP WHERE nest_id=?""",
                    (catalog.revision, catalog.model_dump_json(), nest_id),
                )
                if cursor.rowcount != 1:
                    # Setup owns creation of the configuration row. A fresh
                    # installation still needs to accept the live Runtime
                    # catalog so the Setup UI can become reachable.
                    connection.rollback()
                    return
                connection.commit()
        except sqlite3.Error as error:
            raise NestPersistenceError(str(error)) from error

    def save_resident(self, resident: PersistentResidentState) -> None:
        """Persist only resident presence; Runtime remains home-anchor authority."""
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """UPDATE elfies SET status=?, home_anchor_id=?,
                       updated_at=CURRENT_TIMESTAMP
                       WHERE elfie_id=?""",
                    (
                        _PRESENCE_TO_STATUS[resident.presence],
                        resident.home_anchor_id,
                        resident.elfie_id,
                    ),
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
                    """UPDATE elfies SET status='offline', home_anchor_id=NULL,
                       updated_at=CURRENT_TIMESTAMP WHERE elfie_id=?""",
                    (elfie_id,),
                )
                if cursor.rowcount != 1:
                    raise NestPersistenceError(f"elfie not found: {elfie_id}")
                connection.commit()
        except sqlite3.Error as error:
            raise NestPersistenceError(str(error)) from error

    def save_time_environment(
        self,
        *,
        elapsed_seconds: float,
        clock_paused: bool,
        time_scale: float,
        environment_desired: EnvironmentDesiredState,
        environment_rules: tuple[EnvironmentRule, ...],
    ) -> None:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """UPDATE nest_settings SET clock_anchor_seconds=?, clock_paused=?,
                       time_scale=?, environment_desired_json=?, environment_rules_json=?,
                       updated_at=CURRENT_TIMESTAMP WHERE nest_id=?""",
                    (
                        elapsed_seconds,
                        int(clock_paused),
                        time_scale,
                        environment_desired.model_dump_json(),
                        json.dumps(
                            [rule.model_dump(mode="json") for rule in environment_rules],
                            separators=(",", ":"),
                        ),
                        NestConfig().nest_id,
                    ),
                )
                if cursor.rowcount != 1:
                    connection.rollback()
                    return
                connection.commit()
        except sqlite3.Error as error:
            raise NestPersistenceError(str(error)) from error


def _catalog_from_row(row: sqlite3.Row | None) -> WorldCatalog | None:
    if row is None or row["world_catalog_json"] is None:
        return None
    try:
        return WorldCatalog.model_validate_json(row["world_catalog_json"])
    except ValueError as error:
        raise NestPersistenceError("stored Nest world catalog is invalid") from error


def _environment_desired_from_row(row: sqlite3.Row | None) -> EnvironmentDesiredState:
    if row is None or row["environment_desired_json"] is None:
        return EnvironmentDesiredState()
    try:
        return EnvironmentDesiredState.model_validate_json(row["environment_desired_json"])
    except ValueError as error:
        raise NestPersistenceError("stored Nest environment state is invalid") from error


def _environment_rules_from_row(row: sqlite3.Row | None) -> tuple[EnvironmentRule, ...]:
    if row is None or row["environment_rules_json"] is None:
        return ()
    try:
        values = json.loads(row["environment_rules_json"])
        return tuple(EnvironmentRule.model_validate(value) for value in values)
    except (TypeError, ValueError) as error:
        raise NestPersistenceError("stored Nest environment rules are invalid") from error


def _zone_for_home_anchor(catalog: WorldCatalog | None, home_anchor_id: str) -> str:
    if catalog is None:
        raise NestPersistenceError(
            f"home anchor has no stored world catalog: {home_anchor_id}"
        )
    for zone in catalog.zones:
        for anchor in zone.anchors:
            if (
                anchor.anchor_id == home_anchor_id
                and anchor.kind is AnchorKind.BED
                and anchor.active
            ):
                return zone.zone_id
    raise NestPersistenceError(f"unknown persisted home anchor: {home_anchor_id}")


def _persisted_home_state(
    *,
    elfie_id: str,
    status: str,
    home_anchor_id: str,
    catalog: WorldCatalog | None,
) -> PersistentResidentState:
    return PersistentResidentState(
        elfie_id=elfie_id,
        presence=_STATUS_TO_PRESENCE[status],
        home_zone_id=_zone_for_home_anchor(catalog, home_anchor_id),
        home_anchor_id=home_anchor_id,
    )


__all__ = ("SQLiteNestStateAdapter",)
