"""SQLite connection policy tests for final Elfie memory storage."""

from __future__ import annotations

import sqlite3
import stat
from pathlib import Path

import pytest

from infrastructure.persistence.sqlite_connection import (
    UnsafeSQLitePathError,
    app_sqlite_connection,
)


class RollbackProbeError(Exception):
    """Sentinel exception used to verify transaction rollback."""


def test_connection_enables_rows_foreign_keys_and_private_mode(tmp_path: Path) -> None:
    """Given a file path, When opened, Then SQLite safety policy is active."""
    db_path = tmp_path / "knowledge.sqlite"

    with app_sqlite_connection(db_path) as connection:
        row_factory = connection.row_factory
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]

    assert row_factory is sqlite3.Row
    assert foreign_keys == 1
    assert stat.S_IMODE(db_path.stat().st_mode) == 0o600


def test_connection_rolls_back_failed_transaction(tmp_path: Path) -> None:
    """Given committed schema, When a block fails, Then its write is rolled back."""
    db_path = tmp_path / "knowledge.sqlite"
    with app_sqlite_connection(db_path) as connection:
        connection.execute("CREATE TABLE events (name TEXT NOT NULL)")
        connection.commit()

    with pytest.raises(RollbackProbeError):
        with app_sqlite_connection(db_path) as connection:
            connection.execute("INSERT INTO events (name) VALUES ('draft')")
            raise RollbackProbeError

    with app_sqlite_connection(db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    assert count == 0


def test_connection_rejects_symlink_database(tmp_path: Path) -> None:
    """Given a symlink path, When opened, Then the target is never followed."""
    target = tmp_path / "target.sqlite"
    target.touch()
    link = tmp_path / "knowledge.sqlite"
    link.symlink_to(target)

    with pytest.raises(UnsafeSQLitePathError):
        with app_sqlite_connection(link):
            pass


def test_connection_rejects_symlink_parent_before_writing(tmp_path: Path) -> None:
    """Given a symlink parent, When opened, Then its target remains untouched."""
    target = tmp_path / "target"
    target.mkdir()
    linked_parent = tmp_path / "memory"
    linked_parent.symlink_to(target, target_is_directory=True)

    with pytest.raises(UnsafeSQLitePathError):
        with app_sqlite_connection(linked_parent / "knowledge.sqlite"):
            pass

    assert not (target / "knowledge.sqlite").exists()


def test_connection_rejects_non_directory_ancestor_before_writing(
    tmp_path: Path,
) -> None:
    """Given a file ancestor, When opened, Then a typed path error is raised."""
    file_ancestor = tmp_path / "memory"
    file_ancestor.touch()

    with pytest.raises(UnsafeSQLitePathError):
        with app_sqlite_connection(file_ancestor / "knowledge.sqlite"):
            pass
