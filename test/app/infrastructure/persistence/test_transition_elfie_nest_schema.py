"""Card 8 transition schema tests for final Elfie and Nest root tables."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.infrastructure.persistence.store import get_db, init_db
from app.infrastructure.persistence.transition_elfie_nest_schema import (
    ensure_elfie_nest_transition_schema,
    set_elfie_bed_number,
    set_nest_bed_count,
)


def test_elfie_nest_transition_schema_is_explicit_and_preserves_legacy_tables(
    tmp_path: Path,
) -> None:
    # Given: normal initialization created only the current runtime tables.
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        assert _table_exists(connection, "elfies") is False
        assert _table_exists(connection, "nest_settings") is False

        # When: Card 8 transition DDL is explicitly applied.
        ensure_elfie_nest_transition_schema(connection)

        # Then: new tables exist without deleting legacy runtime tables.
        assert _table_exists(connection, "elfies") is True
        assert _table_exists(connection, "nest_settings") is True
        assert _is_not_null(connection, "elfies", "elfie_id") is True
        assert _is_not_null(connection, "nest_settings", "nest_id") is True
        assert _table_exists(connection, "elfie_registry") is True
        assert _table_exists(connection, "nest_config") is True
        assert _table_exists(connection, "nest_memberships") is True
        assert _table_exists(connection, "nest_home_assignments") is True


def test_elfie_nest_transition_constraints_and_safe_bed_updates(
    tmp_path: Path,
) -> None:
    # Given: a temporary owner, local Nest settings, and two final Elfies.
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        ensure_elfie_nest_transition_schema(connection)
        owner_id = connection.execute(
            """
            INSERT INTO users (username, password_hash, role)
            VALUES ('owner', 'hash', 'owner')
            """
        ).lastrowid
        connection.execute(
            """
            INSERT INTO nest_settings (nest_id, bed_count, tick_interval_sec)
            VALUES ('local', 5, 0.5)
            """
        )
        _insert_elfie(connection, "00000001", owner_id)
        _insert_elfie(connection, "00000002", owner_id)
        set_elfie_bed_number(connection, "00000001", 5)

        # When/Then: invalid IDs, duplicate beds, and out-of-range beds fail.
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO nest_settings (nest_id, bed_count, tick_interval_sec)
                VALUES (NULL, 5, 0.5)
                """
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO elfies
                    (elfie_id, name, owner_user_id, species, adopted_at, status)
                VALUES (NULL, '小狐', ?, 'fox', '2026-07-29T00:00:00Z', 'online')
                """,
                (owner_id,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            _insert_elfie(connection, "elfie_1", owner_id)
        with pytest.raises(sqlite3.IntegrityError):
            set_elfie_bed_number(connection, "00000002", 5)
        with pytest.raises(sqlite3.IntegrityError):
            set_elfie_bed_number(connection, "00000002", 6)

        # When/Then: reducing bed_count below the occupied high bed fails.
        with pytest.raises(sqlite3.IntegrityError):
            set_nest_bed_count(connection, 4)


def _insert_elfie(
    connection: sqlite3.Connection,
    elfie_id: str,
    owner_id: int,
) -> None:
    connection.execute(
        """
        INSERT INTO elfies
            (elfie_id, name, owner_user_id, species, adopted_at, status)
        VALUES (?, '小狐', ?, 'fox', '2026-07-29T00:00:00Z', 'online')
        """,
        (elfie_id, owner_id),
    )


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _is_not_null(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(
        str(row["name"]) == column_name and int(row["notnull"]) == 1
        for row in rows
    )
