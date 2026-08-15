"""SQLite adapter for orchestration-owned semantic Nest state."""

from __future__ import annotations

import json
import sqlite3
from typing import Final

from app.orchestration.nest_session.ports import NestStateStoreError
from infrastructure.persistence.nest_db.sqlite_connection import app_sqlite_connection
from nest.living_rules.models import PersistentResidentState, ResidentPresence
from nest.public import NestConfig, NestSnapshot
from nest.space_facilities.models import AnchorKind, WorldCatalog
from nest.time_environment.models import EnvironmentDesiredState, EnvironmentRule

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

    def __init__(self, db_path: str, *, nest_config: NestConfig | None = None) -> None:
        self._db_path = db_path
        self._nest_config = nest_config or NestConfig()

    def load_snapshot(self) -> NestSnapshot:
        """Restore state without creating or repairing product configuration."""
        defaults = self._nest_config
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
            raise NestStateStoreError(str(error)) from error
        return NestSnapshot(
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

    def save_snapshot(self, snapshot: NestSnapshot) -> None:
        """Persist one complete durable Nest snapshot in one transaction."""
        nest_id = self._nest_config.nest_id
        if snapshot.catalog is not None and snapshot.catalog.nest_id != nest_id:
            raise NestStateStoreError(
                f"unsupported nest_id: {snapshot.catalog.nest_id}"
            )
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """UPDATE nest_settings SET bed_count=?,
                       applied_world_revision=?, world_catalog_json=?,
                       clock_anchor_seconds=?, clock_paused=?, time_scale=?,
                       environment_desired_json=?, environment_rules_json=?,
                       updated_at=CURRENT_TIMESTAMP WHERE nest_id=?""",
                    (
                        snapshot.desired_bed_count,
                        (
                            None
                            if snapshot.catalog is None
                            else snapshot.catalog.revision
                        ),
                        (
                            None
                            if snapshot.catalog is None
                            else snapshot.catalog.model_dump_json()
                        ),
                        snapshot.elapsed_seconds,
                        int(snapshot.clock_paused),
                        snapshot.time_scale,
                        snapshot.environment_desired.model_dump_json(),
                        json.dumps(
                            [
                                rule.model_dump(mode="json")
                                for rule in snapshot.environment_rules
                            ],
                            separators=(",", ":"),
                        ),
                        nest_id,
                    ),
                )
                if cursor.rowcount != 1:
                    connection.rollback()
                    return
                residents = {
                    resident.elfie_id: resident for resident in snapshot.residents
                }
                stored_ids = connection.execute(
                    "SELECT elfie_id FROM elfies"
                ).fetchall()
                for row in stored_ids:
                    elfie_id = str(row["elfie_id"])
                    resident = residents.get(elfie_id)
                    connection.execute(
                        """UPDATE elfies SET status=?, home_anchor_id=?,
                           updated_at=CURRENT_TIMESTAMP WHERE elfie_id=?""",
                        (
                            (
                                _PRESENCE_TO_STATUS[resident.presence]
                                if resident is not None
                                else "offline"
                            ),
                            resident.home_anchor_id if resident is not None else None,
                            elfie_id,
                        ),
                    )
                connection.commit()
        except sqlite3.Error as error:
            raise NestStateStoreError(str(error)) from error


def _catalog_from_row(row: sqlite3.Row | None) -> WorldCatalog | None:
    if row is None or row["world_catalog_json"] is None:
        return None
    try:
        return WorldCatalog.model_validate_json(row["world_catalog_json"])
    except ValueError as error:
        raise NestStateStoreError("stored Nest world catalog is invalid") from error


def _environment_desired_from_row(row: sqlite3.Row | None) -> EnvironmentDesiredState:
    if row is None or row["environment_desired_json"] is None:
        return EnvironmentDesiredState()
    try:
        return EnvironmentDesiredState.model_validate_json(
            row["environment_desired_json"]
        )
    except ValueError as error:
        raise NestStateStoreError("stored Nest environment state is invalid") from error


def _environment_rules_from_row(row: sqlite3.Row | None) -> tuple[EnvironmentRule, ...]:
    if row is None or row["environment_rules_json"] is None:
        return ()
    try:
        values = json.loads(row["environment_rules_json"])
        return tuple(EnvironmentRule.model_validate(value) for value in values)
    except (TypeError, ValueError) as error:
        raise NestStateStoreError(
            "stored Nest environment rules are invalid"
        ) from error


def _zone_for_home_anchor(catalog: WorldCatalog | None, home_anchor_id: str) -> str:
    if catalog is None:
        raise NestStateStoreError(
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
    raise NestStateStoreError(f"unknown persisted home anchor: {home_anchor_id}")


__all__ = ("SQLiteNestStateAdapter",)
