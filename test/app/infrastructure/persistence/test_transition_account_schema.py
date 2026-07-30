"""Card 7 transition schema tests for accounts, sessions, and setup state."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.infrastructure.persistence.account_repository import AccountRepository
from app.infrastructure.persistence.account_storage_cutover import (
    ensure_account_storage_cutover,
)
from app.infrastructure.persistence.store import get_db, init_db
from app.infrastructure.persistence.transition_account_schema import (
    ensure_account_transition_schema,
)


def test_account_transition_schema_is_explicit_and_hash_only(
    tmp_path: Path,
) -> None:
    # Given: the normal root schema has been initialized in a temporary DB.
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        assert _table_exists(connection, "sessions_v2") is False

        # When: Card 7 transition DDL is explicitly applied.
        ensure_account_transition_schema(connection)

        # Then: final account columns and hash-only transition tables exist.
        user_columns = _columns(connection, "users")
        assert {
            "gender",
            "birth_date",
            "presence",
            "last_seen_at",
            "elfie_limit",
        }.issubset(user_columns)
        assert "token_hash" in _columns(connection, "sessions_v2")
        assert "token" not in _columns(connection, "sessions_v2")
        assert _is_not_null(connection, "sessions_v2", "token_hash") is True
        assert {
            "active_task_step",
            "active_task_key",
            "task_state",
            "task_progress",
            "last_error",
        }.issubset(_columns(connection, "local_installations"))
        assert (
            _is_not_null(connection, "local_installations", "installation_id") is True
        )


def test_account_transition_backfills_final_account_fields(tmp_path: Path) -> None:
    # Given: a legacy account with an explicit per-user quota override.
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        user_id = int(
            connection.execute(
                """
                INSERT INTO users
                    (username, password_hash, role, elfie_quota_override)
                VALUES ('alice', 'hash', 'user', 7)
                """
            ).lastrowid
        )

        connection.commit()

    # When: the account storage cutover is applied.
    ensure_account_storage_cutover(db_path)

    with get_db(db_path) as connection:
        # Then: every final field is usable and the repository projects final quota.
        row = connection.execute(
            """
            SELECT gender, birth_date, presence, last_seen_at, elfie_limit
            FROM users WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
        account = AccountRepository(connection).find_by_id(user_id)

        assert row["gender"] is None
        assert row["birth_date"] is None
        assert row["presence"] == "offline"
        assert row["last_seen_at"] is not None
        assert row["elfie_limit"] == 7
        assert account is not None
        assert account.elfie_limit == 7


def test_account_transition_constraints_reject_unsafe_states(
    tmp_path: Path,
) -> None:
    # Given: Card 7 transition DDL and one temporary user.
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        ensure_account_transition_schema(connection)
        user_id = connection.execute(
            """
            INSERT INTO users (username, password_hash, role, elfie_limit)
            VALUES ('owner', 'hash', 'owner', NULL)
            """
        ).lastrowid

        # When/Then: nullable elfie_limit stores runtime-config fallback intent.
        row = connection.execute(
            "SELECT elfie_limit FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        assert row["elfie_limit"] is None

        # When/Then: invalid limits, raw tokens, and illegal setup states fail.
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO sessions_v2 (token_hash, user_id, expires_at)
                VALUES (NULL, ?, '2099-01-01T00:00:00Z')
                """,
                (user_id,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO local_installations (installation_id)
                VALUES (NULL)
                """
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO users (username, password_hash, role, elfie_limit)
                VALUES ('bad-limit', 'hash', 'user', 33)
                """
            )
        with pytest.raises(sqlite3.OperationalError):
            connection.execute(
                """
                INSERT INTO sessions_v2 (token, user_id, expires_at)
                VALUES ('raw-token', ?, '2099-01-01T00:00:00Z')
                """,
                (user_id,),
            )
        connection.execute(
            """
            INSERT INTO sessions_v2 (token_hash, user_id, expires_at)
            VALUES (?, ?, '2099-01-01T00:00:00Z')
            """,
            ("a" * 64, user_id),
        )
        for unsafe_hash in ("raw-token", "", "A" * 64):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO sessions_v2 (token_hash, user_id, expires_at)
                    VALUES (?, ?, '2099-01-01T00:00:00Z')
                    """,
                    (unsafe_hash, user_id),
                )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO local_installations
                    (installation_id, setup_state, setup_step, task_state, task_progress)
                VALUES ('local', 'completed', 'owner', 'invented', 10)
                """
            )


def _columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table_name})")
    }


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
