"""SQLite connection policy tests for app persistence."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.infrastructure.persistence.sqlite_connection import app_sqlite_connection


def test_app_connection_uses_explicit_temp_path_row_factory_and_foreign_keys(
    tmp_path: Path,
) -> None:
    """Given an explicit temp path, When opening app SQLite, Then policy is set."""
    db_path = tmp_path / "app-policy.db"

    with app_sqlite_connection(str(db_path)) as connection:
        assert connection.row_factory is sqlite3.Row
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        connection.execute("CREATE TABLE parents (id INTEGER PRIMARY KEY)")
        connection.execute(
            "CREATE TABLE children ("
            "id INTEGER PRIMARY KEY, "
            "parent_id INTEGER NOT NULL REFERENCES parents(id)"
            ")"
        )
        connection.execute("INSERT INTO parents (id) VALUES (1)")
        connection.commit()
        row = connection.execute("SELECT id FROM parents").fetchone()

    assert db_path.exists()
    assert row["id"] == 1


def test_app_connection_rejects_foreign_key_violations(tmp_path: Path) -> None:
    """Given FK tables, When an orphan child is inserted, Then SQLite rejects it."""
    db_path = tmp_path / "app-fk.db"
    with app_sqlite_connection(str(db_path)) as connection:
        connection.execute("CREATE TABLE parents (id INTEGER PRIMARY KEY)")
        connection.execute(
            "CREATE TABLE children ("
            "id INTEGER PRIMARY KEY, "
            "parent_id INTEGER NOT NULL REFERENCES parents(id)"
            ")"
        )
        connection.commit()

    with pytest.raises(sqlite3.IntegrityError):
        with app_sqlite_connection(str(db_path)) as connection:
            connection.execute(
                "INSERT INTO children (id, parent_id) VALUES (?, ?)",
                (1, 404),
            )


def test_app_connection_rolls_back_on_exception_and_closes(tmp_path: Path) -> None:
    """Given committed schema, When a block raises, Then writes roll back and close."""
    db_path = tmp_path / "app-rollback.db"
    with app_sqlite_connection(str(db_path)) as connection:
        connection.execute("CREATE TABLE events (name TEXT NOT NULL)")
        connection.commit()

    with pytest.raises(RuntimeError):
        with app_sqlite_connection(str(db_path)) as connection:
            connection.execute("INSERT INTO events (name) VALUES (?)", ("draft",))
            raise RuntimeError("force rollback")

    with app_sqlite_connection(str(db_path)) as connection:
        count = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert count == 0

    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
