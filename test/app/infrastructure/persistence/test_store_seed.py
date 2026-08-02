"""Focused tests for environment Owner seed behavior."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.infrastructure.persistence.store import (
    init_db,
    seed_initial_owner_if_env_set,
)
from test.app.interfaces.api._helpers import create_test_owner


def test_creates_owner_from_account_id_env(tmp_path: Path, monkeypatch) -> None:
    # Given
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    monkeypatch.setenv("OWNER_ACCOUNT_ID", "testowner")
    monkeypatch.setenv("OWNER_PASSWORD", "testpass123")

    # When
    result = seed_initial_owner_if_env_set(db_path)

    # Then
    assert result is True
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM users WHERE account_id = ?", ("testowner",)
        ).fetchone()
    assert row is not None
    assert row["account_id"] == "testowner"
    assert row["display_name"] is None
    assert row["role"] == "owner"
    pw_hash: str = row["password_hash"]
    assert pw_hash.startswith("pbkdf2_sha256$260000$")
    assert len(pw_hash.split("$")) == 4


def test_owner_username_env_is_not_a_compatibility_alias(
    tmp_path: Path, monkeypatch
) -> None:
    # Given
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    monkeypatch.setenv("OWNER_USERNAME", "legacy-owner")
    monkeypatch.setenv("OWNER_PASSWORD", "testpass123")

    # When
    result = seed_initial_owner_if_env_set(db_path)

    # Then
    assert result is False
    with sqlite3.connect(db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    assert count == 0


def test_returns_false_when_env_not_set(tmp_path: Path) -> None:
    # Given
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)

    # When / Then
    assert seed_initial_owner_if_env_set(db_path) is False


def test_returns_false_when_account_id_env_partial(tmp_path: Path, monkeypatch) -> None:
    # Given
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    monkeypatch.setenv("OWNER_ACCOUNT_ID", "partial")

    # When / Then
    assert seed_initial_owner_if_env_set(db_path) is False


def test_does_not_reinsert_when_account_id_exists(tmp_path: Path, monkeypatch) -> None:
    # Given
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_test_owner(db_path, "testowner", "testpass123")
    monkeypatch.setenv("OWNER_ACCOUNT_ID", "testowner")
    monkeypatch.setenv("OWNER_PASSWORD", "testpass123")

    # When
    result = seed_initial_owner_if_env_set(db_path)

    # Then
    assert result is False
    with sqlite3.connect(db_path) as connection:
        count = connection.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()[0]
    assert count == 1
