from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.infrastructure.persistence.nest_schema import NestSchemaMigrationError
from app.infrastructure.persistence.store import get_db, migrate_db_if_needed


def _connect(db_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def _create_v6_database(db_path: str, *, bed_count: int = 4) -> None:
    with _connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('owner', 'user')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                nickname TEXT DEFAULT NULL,
                avatar_color INTEGER DEFAULT 0,
                avatar_kind TEXT DEFAULT 'initials'
            );
            CREATE TABLE rooms (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                max_capacity INTEGER NOT NULL DEFAULT 4,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE beds (
                id INTEGER PRIMARY KEY,
                room_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                grid_x INTEGER DEFAULT 0,
                grid_y INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(room_id) REFERENCES rooms(id)
            );
            CREATE TABLE elfie_registry (
                id INTEGER PRIMARY KEY,
                elfie_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                owner_user_id INTEGER,
                anatomy_type TEXT DEFAULT 'biped',
                species_id TEXT NOT NULL DEFAULT 'fox',
                profile_schema_version INTEGER NOT NULL DEFAULT 1,
                config_dir TEXT,
                personality_style TEXT,
                height TEXT DEFAULT 'standard',
                build TEXT DEFAULT 'standard',
                bed_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(owner_user_id) REFERENCES users(id),
                FOREIGN KEY(bed_id) REFERENCES beds(id)
            );
            """
        )
        connection.execute(
            "INSERT INTO rooms (id, name, max_capacity) VALUES (10, 'Main Nest', ?)",
            (bed_count,),
        )
        connection.executemany(
            "INSERT INTO beds (id, room_id, name, grid_x, grid_y) VALUES (?, 10, ?, ?, ?)",
            [
                (index, f"Bed {index}", index * 10, index * 20)
                for index in range(1, bed_count + 1)
            ],
        )
        connection.execute(
            "INSERT INTO elfie_registry (elfie_id, name, bed_id) VALUES (?, ?, ?)",
            ("fox-1", "Fox 1", 1),
        )
        connection.execute("PRAGMA user_version = 6")


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def test_v6_legacy_nest_layout_migrates_to_semantic_tables(tmp_path: Path) -> None:
    # Given
    db_path = str(tmp_path / "legacy.db")
    _create_v6_database(db_path, bed_count=6)

    # When
    migrate_db_if_needed(db_path)

    # Then
    with _connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 13
        assert _table_exists(connection, "nest_config")
        assert _table_exists(connection, "nest_home_assignments")
        anchors = connection.execute(
            "SELECT anchor_id, kind FROM nest_anchors ORDER BY anchor_order"
        ).fetchall()
        home = connection.execute(
            "SELECT elfie_id, home_anchor_id FROM nest_home_assignments"
        ).fetchone()
        old_bed = connection.execute(
            "SELECT grid_x, grid_y FROM beds WHERE id = 1"
        ).fetchone()
    assert len(anchors) == 6
    assert anchors[0]["anchor_id"] == "legacy-room-10/bed-1"
    assert anchors[0]["kind"] == "bed"
    assert home["elfie_id"] == "fox-1"
    assert home["home_anchor_id"] == "legacy-room-10/bed-1"
    assert old_bed["grid_x"] == 10
    assert old_bed["grid_y"] == 20


def test_v6_multiple_rooms_migrate_without_losing_assignments(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "multiple-rooms.db")
    _create_v6_database(db_path, bed_count=2)
    with _connect(db_path) as connection:
        connection.execute(
            "INSERT INTO rooms (id, name, max_capacity) VALUES (20, 'Side Nest', 1)"
        )
        connection.execute(
            """
            INSERT INTO beds (id, room_id, name, grid_x, grid_y)
            VALUES (7, 20, 'Side Bed', 99, 99)
            """
        )
        connection.execute(
            "INSERT INTO elfie_registry (elfie_id, name, bed_id) VALUES (?, ?, ?)",
            ("dog-1", "Dog 1", 7),
        )

    migrate_db_if_needed(db_path)

    with _connect(db_path) as connection:
        zones = connection.execute(
            "SELECT zone_id FROM nest_zones ORDER BY zone_order"
        ).fetchall()
        homes = connection.execute(
            "SELECT elfie_id, home_anchor_id FROM nest_home_assignments ORDER BY elfie_id"
        ).fetchall()
        desired_bed_count = connection.execute(
            "SELECT desired_bed_count FROM nest_config WHERE nest_id = 'local-nest'"
        ).fetchone()[0]
    assert [row["zone_id"] for row in zones] == [
        "legacy-room-10",
        "legacy-room-20",
    ]
    assert [(row["elfie_id"], row["home_anchor_id"]) for row in homes] == [
        ("dog-1", "legacy-room-20/bed-7"),
        ("fox-1", "legacy-room-10/bed-1"),
    ]
    assert desired_bed_count == 4


def test_legacy_app_v9_database_still_receives_semantic_nest_migration(
    tmp_path: Path,
) -> None:
    # Given
    db_path = str(tmp_path / "legacy-app-v9.db")
    _create_v6_database(db_path, bed_count=2)
    with _connect(db_path) as connection:
        connection.execute("PRAGMA user_version = 9")

    # When
    migrate_db_if_needed(db_path)

    # Then
    with _connect(db_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        landing_column = connection.execute("PRAGMA table_info(users)").fetchall()
        home = connection.execute(
            "SELECT elfie_id, home_anchor_id FROM nest_home_assignments"
        ).fetchone()
    assert version == 13
    assert "default_landing_page" in {row["name"] for row in landing_column}
    assert home["elfie_id"] == "fox-1"
    assert home["home_anchor_id"] == "legacy-room-10/bed-1"


def test_v6_legacy_nest_layout_rolls_back_when_bed_count_exceeds_limit(
    tmp_path: Path,
) -> None:
    # Given
    db_path = str(tmp_path / "too-many-beds.db")
    _create_v6_database(db_path, bed_count=33)

    # When / Then
    with pytest.raises(NestSchemaMigrationError, match="exceeds 32"):
        migrate_db_if_needed(db_path)
    with _connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
        assert not _table_exists(connection, "nest_config")
        old_bed_count = connection.execute("SELECT COUNT(*) FROM beds").fetchone()[0]
    assert old_bed_count == 33


def test_v6_legacy_nest_layout_rolls_back_for_dangling_bed_assignment(
    tmp_path: Path,
) -> None:
    # Given
    db_path = str(tmp_path / "dangling-bed.db")
    _create_v6_database(db_path, bed_count=4)
    with _connect(db_path) as connection:
        connection.execute(
            "UPDATE elfie_registry SET bed_id = 999 WHERE elfie_id = 'fox-1'"
        )

    # When / Then
    with pytest.raises(NestSchemaMigrationError, match="dangling bed_id"):
        migrate_db_if_needed(db_path)
    with _connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
        assert not _table_exists(connection, "nest_home_assignments")


def test_v6_legacy_nest_layout_rolls_back_for_duplicate_bed_occupants(
    tmp_path: Path,
) -> None:
    # Given
    db_path = str(tmp_path / "duplicate-occupants.db")
    _create_v6_database(db_path, bed_count=4)
    with _connect(db_path) as connection:
        connection.execute(
            "INSERT INTO elfie_registry (elfie_id, name, bed_id) VALUES (?, ?, ?)",
            ("dog-1", "Dog 1", 1),
        )

    # When / Then
    with pytest.raises(NestSchemaMigrationError, match="duplicate occupants"):
        migrate_db_if_needed(db_path)
    with _connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
        assert not _table_exists(connection, "nest_home_assignments")


def test_persistence_connections_enable_foreign_keys_for_nest_tables(
    tmp_path: Path,
) -> None:
    # Given
    db_path = str(tmp_path / "legacy.db")
    _create_v6_database(db_path, bed_count=4)
    migrate_db_if_needed(db_path)

    # When
    with get_db(db_path) as connection:
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO nest_home_assignments "
                "(elfie_id, home_zone_id, home_anchor_id) VALUES (?, ?, ?)",
                ("missing", "missing-zone", "missing-anchor"),
            )

    # Then
    assert foreign_keys == 1
