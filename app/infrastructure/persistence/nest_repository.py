"""SQLite adapter for the semantic Nest repository."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Final

from app.infrastructure.persistence.nest_schema import (
    DEFAULT_NEST_ID,
    MAX_SEMANTIC_BEDS,
    MIN_SEMANTIC_BEDS,
)

DEFAULT_DESIRED_BED_COUNT: Final = 4
MAX_DESIRED_BED_COUNT: Final = MAX_SEMANTIC_BEDS
MIN_DESIRED_BED_COUNT: Final = MIN_SEMANTIC_BEDS


class NestRepositoryConflictError(RuntimeError):
    """The requested semantic Nest mutation conflicts with current state."""


class NestRepositoryNotFoundError(RuntimeError):
    """The requested semantic Nest record does not exist."""


@dataclass(frozen=True)
class SemanticNestView:
    nest_id: str
    desired_bed_count: int
    applied_world_revision: int | None
    zones: tuple[dict[str, Any], ...]

    def as_rooms_payload(self, *, user_id: int | None = None) -> list[dict[str, Any]]:
        zones = tuple(
            {
                **zone,
                "anchors": tuple(
                    self._anchor_for_user(anchor, user_id=user_id)
                    for anchor in zone["anchors"]
                ),
            }
            for zone in self.zones
        )
        beds: list[dict[str, Any]] = []
        for zone in zones:
            for anchor in zone["anchors"]:
                if anchor["kind"] != "bed":
                    continue
                beds.append(anchor)
        return [
            {
                "id": self.nest_id,
                "name": "Local Nest",
                "desired_bed_count": self.desired_bed_count,
                "applied_world_revision": self.applied_world_revision,
                "beds": beds,
                "zones": list(zones),
            }
        ]

    @staticmethod
    def _anchor_for_user(
        anchor: dict[str, Any],
        *,
        user_id: int | None,
    ) -> dict[str, Any]:
        visible = dict(anchor)
        if user_id is None or anchor["occupant_owner_user_id"] == user_id:
            return visible
        for field in (
            "occupant_id",
            "occupant_name",
            "occupant_owner_user_id",
            "occupant_species_id",
            "occupant_owner_username",
        ):
            visible[field] = None
        return visible


class SQLiteNestRepository:
    """Persist and load semantic Nest state without reading legacy coordinates."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def ensure_default_config(self) -> None:
        self._connection.execute(
            """
            INSERT OR IGNORE INTO nest_config
                (nest_id, desired_bed_count, applied_world_revision)
            VALUES (?, ?, NULL)
            """,
            (DEFAULT_NEST_ID, DEFAULT_DESIRED_BED_COUNT),
        )
        row = self._connection.execute(
            """
            SELECT desired_bed_count
            FROM nest_config
            WHERE nest_id = ?
            """,
            (DEFAULT_NEST_ID,),
        ).fetchone()
        if row is not None and int(row["desired_bed_count"]) < MIN_DESIRED_BED_COUNT:
            self._connection.execute(
                "UPDATE nest_config SET desired_bed_count = ? WHERE nest_id = ?",
                (MIN_DESIRED_BED_COUNT, DEFAULT_NEST_ID),
            )

    def set_desired_bed_count(self, bed_count: int) -> dict[str, int | None]:
        if not MIN_DESIRED_BED_COUNT <= int(bed_count) <= MAX_DESIRED_BED_COUNT:
            raise ValueError(
                f"bed_count 必须在 {MIN_DESIRED_BED_COUNT} 到 {MAX_DESIRED_BED_COUNT} 之间"
            )
        self.ensure_default_config()
        self._connection.execute(
            "UPDATE nest_config SET desired_bed_count = ? WHERE nest_id = ?",
            (int(bed_count), DEFAULT_NEST_ID),
        )
        return self.config_summary()

    def config_summary(self) -> dict[str, int | None]:
        self.ensure_default_config()
        row = self._connection.execute(
            """
            SELECT desired_bed_count, applied_world_revision
            FROM nest_config
            WHERE nest_id = ?
            """,
            (DEFAULT_NEST_ID,),
        ).fetchone()
        if row is None:
            raise NestRepositoryNotFoundError(DEFAULT_NEST_ID)
        return {
            "desired_bed_count": int(row["desired_bed_count"]),
            "applied_world_revision": row["applied_world_revision"],
        }

    def load_view(self) -> SemanticNestView:
        self.ensure_default_config()
        config = self._connection.execute(
            """
            SELECT desired_bed_count, applied_world_revision
            FROM nest_config
            WHERE nest_id = ?
            """,
            (DEFAULT_NEST_ID,),
        ).fetchone()
        zones = self._connection.execute(
            """
            SELECT zone_id, label, zone_order, active
            FROM nest_zones
            WHERE nest_id = ?
            ORDER BY zone_order, zone_id
            """,
            (DEFAULT_NEST_ID,),
        ).fetchall()
        return SemanticNestView(
            nest_id=DEFAULT_NEST_ID,
            desired_bed_count=int(config["desired_bed_count"]),
            applied_world_revision=config["applied_world_revision"],
            zones=tuple(self._zone_payload(zone) for zone in zones),
        )

    def assign_home(self, *, elfie_id: str, anchor_id: str | None) -> None:
        self.ensure_default_config()
        self._ensure_elfie_exists(elfie_id)
        self._connection.execute(
            """
            INSERT OR IGNORE INTO nest_memberships (elfie_id, presence)
            VALUES (?, 'active')
            """,
            (elfie_id,),
        )
        if anchor_id is None:
            self._connection.execute(
                "DELETE FROM nest_home_assignments WHERE elfie_id = ?",
                (elfie_id,),
            )
            return
        anchor = self._bed_anchor(anchor_id)
        occupant = self._connection.execute(
            """
            SELECT elfie_id
            FROM nest_home_assignments
            WHERE home_anchor_id = ? AND elfie_id != ?
            """,
            (anchor_id, elfie_id),
        ).fetchone()
        if occupant is not None:
            raise NestRepositoryConflictError("home anchor already occupied")
        try:
            self._connection.execute(
                """
                INSERT INTO nest_home_assignments
                    (elfie_id, home_zone_id, home_anchor_id)
                VALUES (?, ?, ?)
                ON CONFLICT(elfie_id) DO UPDATE SET
                    home_zone_id = excluded.home_zone_id,
                    home_anchor_id = excluded.home_anchor_id
                """,
                (elfie_id, anchor["zone_id"], anchor_id),
            )
        except sqlite3.IntegrityError as exc:
            raise NestRepositoryConflictError("home anchor already occupied") from exc

    def _zone_payload(self, zone: sqlite3.Row) -> dict[str, Any]:
        anchors = self._connection.execute(
            """
            SELECT a.anchor_id, a.kind, a.label, a.anchor_order, a.active,
                   h.elfie_id AS occupant_id, e.name AS occupant_name,
                   e.owner_user_id AS occupant_owner_user_id,
                   e.species_id AS occupant_species_id, u.username AS occupant_owner_username
            FROM nest_anchors a
            LEFT JOIN nest_home_assignments h ON h.home_anchor_id = a.anchor_id
            LEFT JOIN elfie_registry e ON e.elfie_id = h.elfie_id
            LEFT JOIN users u ON u.id = e.owner_user_id
            WHERE a.zone_id = ?
            ORDER BY a.anchor_order, a.anchor_id
            """,
            (zone["zone_id"],),
        ).fetchall()
        return {
            "zone_id": zone["zone_id"],
            "label": zone["label"],
            "order": int(zone["zone_order"]),
            "active": bool(zone["active"]),
            "anchors": tuple(self._anchor_payload(anchor) for anchor in anchors),
        }

    def _anchor_payload(self, anchor: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": anchor["anchor_id"],
            "anchor_id": anchor["anchor_id"],
            "kind": anchor["kind"],
            "name": anchor["label"],
            "label": anchor["label"],
            "order": int(anchor["anchor_order"]),
            "active": bool(anchor["active"]),
            "occupant_id": anchor["occupant_id"],
            "occupant_name": anchor["occupant_name"],
            "occupant_owner_user_id": anchor["occupant_owner_user_id"],
            "occupant_species_id": anchor["occupant_species_id"],
            "occupant_owner_username": anchor["occupant_owner_username"],
        }

    def _ensure_elfie_exists(self, elfie_id: str) -> None:
        row = self._connection.execute(
            "SELECT elfie_id FROM elfie_registry WHERE elfie_id = ?",
            (elfie_id,),
        ).fetchone()
        if row is None:
            raise NestRepositoryNotFoundError("elfie not found")

    def _bed_anchor(self, anchor_id: str) -> sqlite3.Row:
        row = self._connection.execute(
            """
            SELECT anchor_id, zone_id
            FROM nest_anchors
            WHERE anchor_id = ? AND kind = 'bed' AND active = 1
            """,
            (anchor_id,),
        ).fetchone()
        if row is None:
            raise NestRepositoryNotFoundError("home anchor not found")
        return row
