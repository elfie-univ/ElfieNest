from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.features.administration.owner_service import (
    OwnerDatabaseError,
    get_owner_account,
    recover_owner_account,
)
from app.infrastructure.persistence.store import get_db, hash_password, init_db, verify_password


def test_owner_recovery_preserves_user_id_and_elfie_ownership(tmp_path: Path) -> None:
    # Given
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        owner_id = connection.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'owner')",
            ("old-owner", hash_password("before-reset")),
        ).lastrowid
        connection.execute(
            "INSERT INTO elfie_registry (elfie_id, name, owner_user_id) VALUES (?, ?, ?)",
            ("elfie-1", "艾菲", owner_id),
        )
        connection.commit()

    # When
    recovered = recover_owner_account(db_path, "new-owner", "after-reset")

    # Then
    assert recovered.user_id == owner_id
    assert recovered.username == "new-owner"
    with get_db(db_path) as connection:
        row = connection.execute(
            "SELECT username, password_hash, role, updated_at FROM users WHERE id = ?",
            (owner_id,),
        ).fetchone()
        elfie_owner = connection.execute(
            "SELECT owner_user_id FROM elfie_registry WHERE elfie_id = 'elfie-1'"
        ).fetchone()[0]
    assert row["username"] == "new-owner"
    assert row["role"] == "owner"
    assert row["updated_at"]
    assert verify_password("after-reset", row["password_hash"])
    assert elfie_owner == owner_id


def test_owner_account_never_returns_recoverable_password(tmp_path: Path) -> None:
    # Given
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'owner')",
            ("owner", hash_password("owner-secret")),
        )
        connection.commit()

    # When
    account = get_owner_account(db_path)

    # Then
    assert account.username == "owner"
    assert account.password_status == "已设置（不可查看）"
    assert not hasattr(account, "password_hash")


def test_legacy_owner_is_migrated_to_single_owner(tmp_path: Path) -> None:
    # Given
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(str(db_path)) as connection:
        connection.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, "
            "password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('owner', 'user')), "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        connection.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'owner')",
            ("legacy-owner", hash_password("legacy-secret")),
        )

    # When
    init_db(str(db_path))

    # Then
    with get_db(str(db_path)) as connection:
        roles = connection.execute(
            "SELECT role FROM users ORDER BY id"
        ).fetchall()
    assert [row[0] for row in roles] == ["owner"]


def test_empty_database_is_not_initialized_by_owner_lookup(tmp_path: Path) -> None:
    # Given
    db_path = tmp_path / "empty.db"
    db_path.touch()

    # When / Then
    with pytest.raises(OwnerDatabaseError):
        get_owner_account(str(db_path))
    assert db_path.stat().st_size == 0


def test_legacy_users_without_timestamps_can_migrate(tmp_path: Path) -> None:
    # Given
    db_path = tmp_path / "legacy-no-timestamps.db"
    with sqlite3.connect(str(db_path)) as connection:
        connection.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, "
            "password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('owner', 'user')))"
        )
        connection.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'owner')",
            ("legacy-owner", hash_password("legacy-secret")),
        )

    # When
    init_db(str(db_path))

    # Then
    account = get_owner_account(str(db_path))
    assert account.username == "legacy-owner"
    assert account.created_at
    assert account.updated_at
