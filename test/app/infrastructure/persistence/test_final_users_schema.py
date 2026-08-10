"""Focused contract tests for the final ``users`` table."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Final

import pytest

from app.infrastructure.persistence.final_schema import create_final_nest_database
from app.infrastructure.persistence.store import LegacyDataRootError, init_db
from infrastructure.persistence.sqlite_connection import app_sqlite_connection

EXPECTED_USER_COLUMNS: Final = (
    "id",
    "account_id",
    "display_name",
    "avatar_color",
    "avatar_kind",
    "avatar_path",
    "gender",
    "birth_date",
    "role",
    "password_hash",
    "presence",
    "last_seen_at",
    "elfie_limit",
    "default_landing_page",
    "theme_key",
    "language",
    "created_at",
    "updated_at",
)


def test_final_users_defaults_and_existing_constraints_when_created_fresh(
    tmp_path: Path,
) -> None:
    # Given: the current final schema on a fresh isolated database.
    db_path = create_final_nest_database(tmp_path / "nest.db")

    # When: a user row is inserted with only the currently required account fields.
    with app_sqlite_connection(db_path) as connection:
        user_id = _insert_user(connection, "owner01", "owner")
        row = connection.execute(
            "SELECT avatar_color, avatar_kind, presence, elfie_limit, "
            "default_landing_page, theme_key, language FROM users WHERE id=?",
            (user_id,),
        ).fetchone()

        # Then: the established closed defaults and path constraints are preserved.
        assert tuple(row) == (
            0,
            "initials",
            "offline",
            None,
            "manage",
            "warm-paper",
            "zh-CN",
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE users SET avatar_path = ? WHERE id = ?",
                ("../avatar.png", user_id),
            )


def test_final_users_have_exact_canonical_column_order(tmp_path: Path) -> None:
    # Given: the final schema on a fresh isolated database.
    db_path = create_final_nest_database(tmp_path / "nest.db")

    # When: SQLite reports the physical users table column order.
    with app_sqlite_connection(db_path) as connection:
        columns = _ordered_columns(connection)

    # Then: the order exactly matches the final account contract.
    assert columns == EXPECTED_USER_COLUMNS


def test_final_users_reject_invalid_identity_values_when_inserted_directly(
    tmp_path: Path,
) -> None:
    # Given: the final schema on a fresh isolated database.
    db_path = create_final_nest_database(tmp_path / "nest.db")
    with app_sqlite_connection(db_path) as connection:
        _insert_user(connection, "owner01", "owner")

        # When/Then: malformed account IDs and display names are rejected.
        for account_id in ("", "  ", "ab", "a" * 33, " owner02 "):
            with pytest.raises(sqlite3.IntegrityError):
                _insert_user(connection, account_id, "user")
        with pytest.raises(sqlite3.IntegrityError):
            _insert_user(connection, "owner01", "user")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO users(account_id,display_name,password_hash,role) "
                "VALUES(?,?,?,'user')",
                ("member01", "x" * 65, "password-hash"),
            )


def test_final_users_have_no_legacy_account_columns(tmp_path: Path) -> None:
    # Given: the final schema on a fresh isolated database.
    db_path = create_final_nest_database(tmp_path / "nest.db")

    # When/Then: legacy account columns are not selectable.
    with app_sqlite_connection(db_path) as connection:
        assert "username" not in _ordered_columns(connection)
        assert "nickname" not in _ordered_columns(connection)
        with pytest.raises(sqlite3.OperationalError, match="no such column"):
            connection.execute("SELECT username FROM users").fetchone()
        with pytest.raises(sqlite3.OperationalError, match="no such column"):
            connection.execute("SELECT nickname FROM users").fetchone()


def test_final_users_accept_admin_and_enforce_admin_and_total_caps(
    tmp_path: Path,
) -> None:
    db_path = create_final_nest_database(tmp_path / "nest.db")

    with app_sqlite_connection(db_path) as connection:
        _insert_user(connection, "owner01", "owner")
        with pytest.raises(sqlite3.IntegrityError):
            _insert_user(connection, "unknown01", "manager")
        for index in range(1, 6):
            _insert_user(connection, f"admin{index:02d}", "admin")
        with pytest.raises(sqlite3.IntegrityError):
            _insert_user(connection, "admin06", "admin")

        for index in range(1, 11):
            _insert_user(connection, f"user{index:02d}", "user")
        with pytest.raises(sqlite3.IntegrityError):
            _insert_user(connection, "user11", "user")


def test_final_users_allow_fifteen_users_without_independent_user_cap(
    tmp_path: Path,
) -> None:
    db_path = create_final_nest_database(tmp_path / "nest.db")

    with app_sqlite_connection(db_path) as connection:
        _insert_user(connection, "owner01", "owner")
        for index in range(1, 16):
            _insert_user(connection, f"user{index:02d}", "user")
        count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    assert count == 16


def test_final_users_protect_the_existing_owner_from_loss(tmp_path: Path) -> None:
    db_path = create_final_nest_database(tmp_path / "nest.db")

    with app_sqlite_connection(db_path) as connection:
        owner_id = _insert_user(connection, "owner01", "owner")
        with pytest.raises(sqlite3.IntegrityError):
            _insert_user(connection, "owner02", "owner")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE users SET role='admin' WHERE id=?", (owner_id,))
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM users WHERE id=?", (owner_id,))


def test_init_db_rejects_previous_role_constraint_before_writing(
    tmp_path: Path,
) -> None:
    db_path = create_final_nest_database(tmp_path / "nest.db")
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA writable_schema=ON")
        connection.execute(
            "UPDATE sqlite_master SET sql=REPLACE(sql, ?, ?) WHERE name='users'",
            ("role IN ('owner','admin','user')", "role IN ('owner','user')"),
        )
        schema_version = int(connection.execute("PRAGMA schema_version").fetchone()[0])
        connection.execute(f"PRAGMA schema_version = {schema_version + 1}")
        connection.commit()

    before_hash = hashlib.sha256(db_path.read_bytes()).hexdigest()
    with pytest.raises(LegacyDataRootError):
        init_db(str(db_path))
    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == before_hash


def _ordered_columns(connection: sqlite3.Connection) -> tuple[str, ...]:
    return tuple(str(row[1]) for row in connection.execute("PRAGMA table_info(users)"))


def _insert_user(connection: sqlite3.Connection, account_id: str, role: str) -> int:
    cursor = connection.execute(
        "INSERT INTO users(account_id,password_hash,role) VALUES(?,?,?)",
        (account_id, "password-hash", role),
    )
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)
