"""Explicit transition DDL for Card 8 Elfie and Nest root storage."""

from __future__ import annotations

import sqlite3


class TransitionNestWriteError(RuntimeError):
    """Raised when a Card 8 transition helper cannot update its target row."""


def ensure_elfie_nest_transition_schema(connection: sqlite3.Connection) -> None:
    """Create Card 8 transition tables without deleting legacy Nest tables."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS nest_settings (
            nest_id TEXT NOT NULL PRIMARY KEY CHECK(nest_id = 'local'),
            bed_count INTEGER NOT NULL CHECK(bed_count BETWEEN 4 AND 32),
            tick_interval_sec REAL NOT NULL CHECK(tick_interval_sec > 0),
            max_elfies INTEGER CHECK(max_elfies IS NULL OR max_elfies >= 0),
            applied_world_revision INTEGER,
            clock_anchor_seconds REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS elfies (
            elfie_id TEXT NOT NULL PRIMARY KEY
                CHECK(elfie_id GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'),
            name TEXT NOT NULL,
            owner_user_id INTEGER NOT NULL,
            species TEXT NOT NULL,
            gender TEXT,
            birth_date TEXT,
            adopted_at TEXT NOT NULL,
            bed_number INTEGER CHECK(bed_number IS NULL OR bed_number BETWEEN 1 AND 32),
            status TEXT NOT NULL CHECK(status IN ('online', 'away', 'offline')),
            summary TEXT,
            main_food TEXT,
            emergency_food TEXT,
            other_foods_json TEXT NOT NULL DEFAULT '[]'
                CHECK(json_valid(other_foods_json)
                    AND json_type(other_foods_json) = 'array'),
            food_updated_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(owner_user_id) REFERENCES users(id)
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_elfies_bed_number
        ON elfies(bed_number)
        WHERE bed_number IS NOT NULL
        """
    )
    _ensure_bed_triggers(connection)


def set_elfie_bed_number(
    connection: sqlite3.Connection,
    elfie_id: str,
    bed_number: int | None,
) -> None:
    """Update one Elfie's bed assignment inside the caller's transaction."""
    cursor = connection.execute(
        """
        UPDATE elfies
        SET bed_number = ?, updated_at = CURRENT_TIMESTAMP
        WHERE elfie_id = ?
        """,
        (bed_number, elfie_id),
    )
    if cursor.rowcount != 1:
        raise TransitionNestWriteError(f"Elfie not found: {elfie_id}")


def set_nest_bed_count(connection: sqlite3.Connection, bed_count: int) -> None:
    """Update local bed capacity without orphaning occupied bed numbers."""
    cursor = connection.execute(
        """
        UPDATE nest_settings
        SET bed_count = ?, updated_at = CURRENT_TIMESTAMP
        WHERE nest_id = 'local'
        """,
        (bed_count,),
    )
    if cursor.rowcount != 1:
        raise TransitionNestWriteError("local Nest settings row is missing")


def _ensure_bed_triggers(connection: sqlite3.Connection) -> None:
    for action in ("INSERT", "UPDATE OF bed_number"):
        trigger_name = f"trg_elfies_bed_within_count_{action.lower().split()[0]}"
        connection.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS {trigger_name}
            BEFORE {action} ON elfies
            WHEN NEW.bed_number IS NOT NULL
             AND (
                (SELECT bed_count FROM nest_settings WHERE nest_id = 'local') IS NULL
                OR NEW.bed_number > (
                    SELECT bed_count FROM nest_settings WHERE nest_id = 'local'
                )
             )
            BEGIN
                SELECT RAISE(ABORT, 'bed_number exceeds local Nest bed_count');
            END
            """
        )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_nest_settings_bed_count_occupied
        BEFORE UPDATE OF bed_count ON nest_settings
        WHEN NEW.nest_id = 'local'
         AND EXISTS (
            SELECT 1 FROM elfies
            WHERE bed_number IS NOT NULL AND bed_number > NEW.bed_count
         )
        BEGIN
            SELECT RAISE(ABORT, 'bed_count is below occupied bed_number');
        END
        """
    )
