"""Database-path-backed adapter for the orchestration Nest repository port."""

from __future__ import annotations

import sqlite3

from app.infrastructure.persistence.nest_repository import SQLiteNestRepository
from app.infrastructure.persistence.store import get_db
from nest.state.models import (
    AnchorKind,
    InteractionAnchor,
    PersistentResidentState,
    ResidentPresence,
    WorldCatalog,
    ZoneDescriptor,
)
from nest.state.repository import (
    NestPersistenceError,
    NestPersistenceSnapshot,
)


class SQLiteNestStateRepository:
    """Open one SQLite transaction per orchestration persistence mutation."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def load_snapshot(self) -> NestPersistenceSnapshot:
        try:
            with get_db(self._db_path) as connection:
                repository = SQLiteNestRepository(connection)
                repository.ensure_default_config()
                config = connection.execute(
                    """
                    SELECT nest_id, desired_bed_count, applied_world_revision,
                           clock_anchor_seconds
                    FROM nest_config
                    LIMIT 1
                    """
                ).fetchone()
                catalog = self._load_catalog(
                    connection,
                    nest_id=str(config["nest_id"]),
                    revision=config["applied_world_revision"],
                )
                residents = self._load_residents(connection)
                connection.commit()
        except sqlite3.Error as exc:
            raise NestPersistenceError(str(exc)) from exc
        return NestPersistenceSnapshot(
            desired_bed_count=int(config["desired_bed_count"]),
            elapsed_seconds=float(config["clock_anchor_seconds"]),
            catalog=catalog,
            residents=residents,
        )

    def save_catalog(self, catalog: WorldCatalog) -> None:
        try:
            with get_db(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                SQLiteNestRepository(connection).ensure_default_config()
                connection.execute("UPDATE nest_zones SET active = 0")
                connection.execute("UPDATE nest_anchors SET active = 0")
                for zone in catalog.zones:
                    connection.execute(
                        """
                        INSERT INTO nest_zones
                            (zone_id, nest_id, label, zone_order, active)
                        VALUES (?, ?, ?, ?, 1)
                        ON CONFLICT(zone_id) DO UPDATE SET
                            nest_id = excluded.nest_id,
                            label = excluded.label,
                            zone_order = excluded.zone_order,
                            active = 1
                        """,
                        (zone.zone_id, catalog.nest_id, zone.label, zone.order),
                    )
                    for anchor in zone.anchors:
                        connection.execute(
                            """
                            INSERT INTO nest_anchors
                                (anchor_id, zone_id, kind, label, anchor_order, active)
                            VALUES (?, ?, ?, ?, ?, ?)
                            ON CONFLICT(anchor_id) DO UPDATE SET
                                zone_id = excluded.zone_id,
                                kind = excluded.kind,
                                label = excluded.label,
                                anchor_order = excluded.anchor_order,
                                active = excluded.active
                            """,
                            (
                                anchor.anchor_id,
                                zone.zone_id,
                                anchor.kind.value,
                                anchor.label,
                                anchor.order,
                                int(anchor.active),
                            ),
                        )
                connection.execute(
                    """
                    UPDATE nest_config
                    SET applied_world_revision = ?
                    WHERE nest_id = ?
                    """,
                    (catalog.revision, catalog.nest_id),
                )
                connection.commit()
        except sqlite3.Error as exc:
            raise NestPersistenceError(str(exc)) from exc

    def save_resident(self, resident: PersistentResidentState) -> None:
        try:
            with get_db(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT INTO nest_memberships (elfie_id, presence)
                    VALUES (?, ?)
                    ON CONFLICT(elfie_id) DO UPDATE SET
                        presence = excluded.presence
                    """,
                    (resident.elfie_id, resident.presence.value),
                )
                if resident.home_anchor_id is None or resident.home_zone_id is None:
                    connection.execute(
                        "DELETE FROM nest_home_assignments WHERE elfie_id = ?",
                        (resident.elfie_id,),
                    )
                else:
                    connection.execute(
                        """
                        INSERT INTO nest_home_assignments
                            (elfie_id, home_zone_id, home_anchor_id)
                        VALUES (?, ?, ?)
                        ON CONFLICT(elfie_id) DO UPDATE SET
                            home_zone_id = excluded.home_zone_id,
                            home_anchor_id = excluded.home_anchor_id
                        """,
                        (
                            resident.elfie_id,
                            resident.home_zone_id,
                            resident.home_anchor_id,
                        ),
                    )
                connection.commit()
        except sqlite3.Error as exc:
            raise NestPersistenceError(str(exc)) from exc

    def remove_resident(self, elfie_id: str) -> None:
        try:
            with get_db(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "DELETE FROM nest_home_assignments WHERE elfie_id = ?",
                    (elfie_id,),
                )
                connection.execute(
                    "DELETE FROM nest_memberships WHERE elfie_id = ?",
                    (elfie_id,),
                )
                connection.commit()
        except sqlite3.Error as exc:
            raise NestPersistenceError(str(exc)) from exc

    @staticmethod
    def _load_catalog(
        connection: sqlite3.Connection,
        *,
        nest_id: str,
        revision: int | None,
    ) -> WorldCatalog | None:
        zone_rows = connection.execute(
            """
            SELECT zone_id, label, zone_order
            FROM nest_zones
            WHERE nest_id = ? AND active = 1
            ORDER BY zone_order, zone_id
            """,
            (nest_id,),
        ).fetchall()
        if not zone_rows:
            return None
        zones: list[ZoneDescriptor] = []
        for zone_row in zone_rows:
            anchor_rows = connection.execute(
                """
                SELECT anchor_id, kind, label, anchor_order, active
                FROM nest_anchors
                WHERE zone_id = ?
                ORDER BY anchor_order, anchor_id
                """,
                (zone_row["zone_id"],),
            ).fetchall()
            zones.append(
                ZoneDescriptor(
                    zone_id=str(zone_row["zone_id"]),
                    label=str(zone_row["label"]),
                    order=int(zone_row["zone_order"]),
                    anchors=tuple(
                        InteractionAnchor(
                            anchor_id=str(anchor["anchor_id"]),
                            kind=AnchorKind(str(anchor["kind"])),
                            label=str(anchor["label"]),
                            order=int(anchor["anchor_order"]),
                            active=bool(anchor["active"]),
                        )
                        for anchor in anchor_rows
                    ),
                )
            )
        return WorldCatalog(
            nest_id=nest_id,
            revision=int(revision or 0),
            zones=tuple(zones),
        )

    @staticmethod
    def _load_residents(
        connection: sqlite3.Connection,
    ) -> tuple[PersistentResidentState, ...]:
        rows = connection.execute(
            """
            SELECT m.elfie_id, m.presence,
                   h.home_zone_id, h.home_anchor_id
            FROM nest_memberships m
            LEFT JOIN nest_home_assignments h ON h.elfie_id = m.elfie_id
            ORDER BY m.elfie_id
            """
        ).fetchall()
        return tuple(
            PersistentResidentState(
                elfie_id=str(row["elfie_id"]),
                presence=ResidentPresence(str(row["presence"])),
                home_zone_id=row["home_zone_id"],
                home_anchor_id=row["home_anchor_id"],
            )
            for row in rows
        )


__all__ = ("SQLiteNestStateRepository",)
