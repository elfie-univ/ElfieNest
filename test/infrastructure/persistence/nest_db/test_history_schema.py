"""Final history.sqlite schema contract tests."""

from __future__ import annotations

import sqlite3
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from infrastructure.persistence.nest_db import history_schema
from infrastructure.persistence.nest_db.history_schema import (
    HISTORY_FILENAME,
    InvalidHistoryPathError,
    create_history_schema,
)
from infrastructure.persistence.nest_db.sqlite_connection import UnsafeSQLitePathError

EXPECTED_TABLES = {
    "attachments",
    "conversation_participants",
    "conversations",
    "external_channel_accounts",
    "ingestion_offsets",
    "messages",
    "self_channel_accounts",
}


def test_creates_exact_seven_tables_when_path_is_final(tmp_path: Path) -> None:
    """Given history.sqlite, When initialized, Then exactly seven tables exist."""
    # Given
    db_path = tmp_path / "elfies" / "00000001" / "conversations" / HISTORY_FILENAME

    # When
    create_history_schema(db_path)

    # Then
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    assert {str(row[0]) for row in rows} == EXPECTED_TABLES
    assert stat.S_IMODE(db_path.stat().st_mode) == 0o600


def test_history_schema_skips_unavailable_windows_chmod(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: Windows has no follow_symlinks implementation for os.chmod.
    def unsupported_chmod(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Windows must not call POSIX-only chmod options")

    monkeypatch.setattr(
        history_schema,
        "os",
        SimpleNamespace(name="nt", chmod=unsupported_chmod),
    )

    # When: the final history database is initialized on that platform.
    db_path = tmp_path / "elfies" / "00000001" / "conversations" / HISTORY_FILENAME
    create_history_schema(db_path)

    # Then: schema creation reaches SQLite without the unsupported call.
    assert db_path.is_file()


def test_is_idempotent_when_initialized_twice(tmp_path: Path) -> None:
    """Given an initialized database, When initialized again, Then it stays valid."""
    # Given
    db_path = tmp_path / HISTORY_FILENAME
    create_history_schema(db_path)

    # When
    create_history_schema(db_path)

    # Then
    with sqlite3.connect(db_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()
    assert count is not None
    assert int(count[0]) == len(EXPECTED_TABLES)


def test_rejects_nonfinal_database_name_before_writing(tmp_path: Path) -> None:
    """Given a transitional filename, When initialized, Then no file is written."""
    # Given
    db_path = tmp_path / "history_v2.sqlite"

    # When / Then
    with pytest.raises(InvalidHistoryPathError):
        create_history_schema(db_path)
    assert not db_path.exists()


def test_rejects_symlink_database_without_touching_target(tmp_path: Path) -> None:
    """Given a database symlink, When initialized, Then its target is unchanged."""
    # Given
    target = tmp_path / "sentinel.txt"
    target.write_text("safe", encoding="utf-8")
    db_path = tmp_path / HISTORY_FILENAME
    db_path.symlink_to(target)

    # When / Then
    with pytest.raises(UnsafeSQLitePathError):
        create_history_schema(db_path)
    assert target.read_text(encoding="utf-8") == "safe"


def test_rejects_symlink_ancestor_before_creating_target_directories(
    tmp_path: Path,
) -> None:
    """Given a linked ancestor, When initialized, Then its target stays untouched."""
    # Given
    target_root = tmp_path / "outside"
    target_root.mkdir()
    linked_root = tmp_path / "linked"
    linked_root.symlink_to(target_root, target_is_directory=True)
    db_path = linked_root / "elfies" / "00000001" / "conversations" / HISTORY_FILENAME

    # When / Then
    with pytest.raises(UnsafeSQLitePathError):
        create_history_schema(db_path)
    assert list(target_root.iterdir()) == []
