"""SQLite Nest semantic schema and v7 migration."""

from __future__ import annotations

import sqlite3
from typing import Final

DEFAULT_NEST_ID: Final = "local-nest"
MAX_SEMANTIC_BEDS: Final = 32


class NestSchemaMigrationError(RuntimeError):
    """旧 Nest 布局无法无损迁移到语义表。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

    def __str__(self) -> str:
        return self.reason


def ensure_nest_semantic_tables(connection: sqlite3.Connection) -> None:
    """Create semantic Nest tables without reading legacy coordinates."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS nest_config (
            nest_id TEXT PRIMARY KEY,
            desired_bed_count INTEGER NOT NULL CHECK(desired_bed_count BETWEEN 1 AND 32),
            applied_world_revision INTEGER,
            clock_anchor_seconds REAL NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS nest_zones (
            zone_id TEXT PRIMARY KEY,
            nest_id TEXT NOT NULL,
            label TEXT NOT NULL,
            zone_order INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(nest_id) REFERENCES nest_config(nest_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS nest_anchors (
            anchor_id TEXT PRIMARY KEY,
            zone_id TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('bed', 'chair', 'door', 'activity')),
            label TEXT NOT NULL,
            anchor_order INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(zone_id) REFERENCES nest_zones(zone_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS nest_memberships (
            elfie_id TEXT PRIMARY KEY,
            presence TEXT NOT NULL CHECK(presence IN ('active', 'away', 'pending_runtime')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(elfie_id) REFERENCES elfie_registry(elfie_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS nest_home_assignments (
            elfie_id TEXT PRIMARY KEY,
            home_zone_id TEXT NOT NULL,
            home_anchor_id TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(elfie_id) REFERENCES nest_memberships(elfie_id),
            FOREIGN KEY(home_zone_id) REFERENCES nest_zones(zone_id),
            FOREIGN KEY(home_anchor_id) REFERENCES nest_anchors(anchor_id)
        )
        """
    )


def ensure_legacy_nest_tables(connection: sqlite3.Connection) -> None:
    """Create legacy rooms/beds tables retained for compatibility."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            max_capacity INTEGER NOT NULL DEFAULT 4,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS beds (
            id INTEGER PRIMARY KEY,
            room_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            grid_x INTEGER DEFAULT 0,
            grid_y INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(room_id) REFERENCES rooms(id)
        )
        """
    )


def migrate_legacy_nest_layout_to_semantic_tables(
    connection: sqlite3.Connection,
) -> None:
    """Migrate v6 rooms/beds/registry data to semantic Nest tables."""
    _validate_legacy_layout(connection)
    ensure_nest_semantic_tables(connection)
    bed_count = _legacy_bed_count(connection)
    desired_bed_count = max(1, bed_count)
    connection.execute(
        """
        INSERT OR IGNORE INTO nest_config
            (nest_id, desired_bed_count, applied_world_revision, clock_anchor_seconds)
        VALUES (?, ?, NULL, 0)
        """,
        (DEFAULT_NEST_ID, desired_bed_count),
    )
    _copy_legacy_room_and_bed_catalog(connection)
    _copy_legacy_memberships(connection)
    _copy_legacy_home_assignments(connection)
    connection.execute("PRAGMA user_version = 7")


def _validate_legacy_layout(connection: sqlite3.Connection) -> None:
    bed_count = _legacy_bed_count(connection)
    if bed_count > MAX_SEMANTIC_BEDS:
        raise NestSchemaMigrationError(
            f"legacy bed count {bed_count} exceeds 32; migration stopped"
        )
    dangling = int(
        connection.execute(
            """
            SELECT COUNT(*)
            FROM elfie_registry e
            LEFT JOIN beds b ON b.id = e.bed_id
            WHERE e.bed_id IS NOT NULL AND b.id IS NULL
            """
        ).fetchone()[0]
    )
    if dangling:
        raise NestSchemaMigrationError("legacy elfie_registry has dangling bed_id")
    duplicates = int(
        connection.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT bed_id
                FROM elfie_registry
                WHERE bed_id IS NOT NULL
                GROUP BY bed_id
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    )
    if duplicates:
        raise NestSchemaMigrationError("legacy bed assignment has duplicate occupants")


def _legacy_bed_count(connection: sqlite3.Connection) -> int:
    return int(connection.execute("SELECT COUNT(*) FROM beds").fetchone()[0])


def _copy_legacy_room_and_bed_catalog(connection: sqlite3.Connection) -> None:
    rooms = connection.execute("SELECT id, name FROM rooms ORDER BY id").fetchall()
    anchor_order = 0
    for zone_order, room in enumerate(rooms, start=1):
        room_id = int(room["id"])
        zone_id = _zone_id(room_id)
        connection.execute(
            """
            INSERT OR IGNORE INTO nest_zones
                (zone_id, nest_id, label, zone_order, active)
            VALUES (?, ?, ?, ?, 1)
            """,
            (
                zone_id,
                DEFAULT_NEST_ID,
                str(room["name"]),
                zone_order,
            ),
        )
        beds = connection.execute(
            "SELECT id, name FROM beds WHERE room_id = ? ORDER BY id",
            (room_id,),
        ).fetchall()
        for bed in beds:
            connection.execute(
                """
                INSERT OR IGNORE INTO nest_anchors
                    (anchor_id, zone_id, kind, label, anchor_order, active)
                VALUES (?, ?, 'bed', ?, ?, 1)
                """,
                (
                    _anchor_id(room_id, int(bed["id"])),
                    zone_id,
                    str(bed["name"]),
                    anchor_order,
                ),
            )
            anchor_order += 1


def _copy_legacy_memberships(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        "SELECT elfie_id FROM elfie_registry ORDER BY id"
    ).fetchall()
    for row in rows:
        connection.execute(
            """
            INSERT OR IGNORE INTO nest_memberships (elfie_id, presence)
            VALUES (?, 'active')
            """,
            (str(row["elfie_id"]),),
        )


def _copy_legacy_home_assignments(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """
        SELECT e.elfie_id, b.id AS bed_id, b.room_id
        FROM elfie_registry e
        JOIN beds b ON b.id = e.bed_id
        WHERE e.bed_id IS NOT NULL
        ORDER BY e.id
        """
    ).fetchall()
    for row in rows:
        room_id = int(row["room_id"])
        connection.execute(
            """
            INSERT INTO nest_home_assignments
                (elfie_id, home_zone_id, home_anchor_id)
            VALUES (?, ?, ?)
            """,
            (
                str(row["elfie_id"]),
                _zone_id(room_id),
                _anchor_id(room_id, int(row["bed_id"])),
            ),
        )


def _zone_id(room_id: int) -> str:
    return f"legacy-room-{room_id}"


def _anchor_id(room_id: int, bed_id: int) -> str:
    return f"{_zone_id(room_id)}/bed-{bed_id}"
