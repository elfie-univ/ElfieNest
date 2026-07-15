from __future__ import annotations

import sqlite3
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

from elfienest.operations.admin_service import (
    AdminAccount,
    AdminNotFoundError,
    AdminSelectionRequiredError,
    DatabaseOperationError,
    DatabaseSchemaError,
    DatabaseUnavailableError,
    InvalidPasswordError,
    NotAdministratorError,
    list_admin_accounts,
    reset_admin_password,
)
from elfienest.persistence.store import (
    get_db,
    hash_password,
    init_db,
    verify_password,
)


def test_password_hash_round_trip_characterizes_existing_store() -> None:
    # Given
    password = "before-reset"

    # When
    password_hash = hash_password(password)

    # Then
    assert verify_password(password, password_hash) is True
    assert verify_password("different-password", password_hash) is False


def test_sessions_are_scoped_to_existing_user_id(tmp_path: Path) -> None:
    # Given
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as conn:
        user_id = conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
            ("admin", hash_password("before-reset")),
        ).lastrowid
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            ("admin-session", user_id, 12345.0),
        )
        conn.commit()

    # When
    with get_db(db_path) as conn:
        session_user_id = conn.execute(
            "SELECT user_id FROM sessions WHERE token = ?", ("admin-session",)
        ).fetchone()[0]

    # Then
    assert session_user_id == user_id


def _create_user(
    db_path: str, username: str, password: str, role: str = "admin"
) -> int:
    with get_db(db_path) as conn:
        user_id = conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, hash_password(password), role),
        ).lastrowid
        conn.commit()
    assert user_id is not None
    return int(user_id)


def _initialized_db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    return db_path


def _create_session(db_path: str, token: str, user_id: int) -> None:
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, 12345.0),
        )
        conn.commit()


def test_list_admin_accounts_returns_only_frozen_non_sensitive_data(
    tmp_path: Path,
) -> None:
    # Given
    db_path = _initialized_db(tmp_path)
    _create_user(db_path, "admin", "before-reset")
    _create_user(db_path, "member", "member-password", role="user")

    # When
    accounts = list_admin_accounts(db_path)

    # Then
    assert len(accounts) == 1
    assert accounts[0].username == "admin"
    assert {field.name for field in fields(accounts[0])} == {
        "user_id",
        "username",
        "created_at",
    }
    assert not hasattr(accounts[0], "password_hash")
    assert not hasattr(accounts[0], "role")
    with pytest.raises(FrozenInstanceError):
        accounts[0].username = "changed"


def test_list_admin_accounts_supports_legacy_users_without_created_at(
    tmp_path: Path,
) -> None:
    # Given
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, "
            "password_hash TEXT, role TEXT)"
        )
        conn.execute(
            "CREATE TABLE sessions (token TEXT PRIMARY KEY, user_id INTEGER, "
            "expires_at REAL)"
        )
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
            ("legacy", hash_password("before-reset")),
        )

    # When
    accounts = list_admin_accounts(str(db_path))

    # Then
    assert accounts == (AdminAccount(user_id=1, username="legacy", created_at=None),)


def test_missing_database_is_rejected_without_creating_file(tmp_path: Path) -> None:
    # Given
    db_path = tmp_path / "missing.db"

    # When / Then
    with pytest.raises(DatabaseUnavailableError):
        list_admin_accounts(str(db_path))
    assert not db_path.exists()


def test_malformed_database_raises_typed_schema_error(tmp_path: Path) -> None:
    # Given
    db_path = tmp_path / "malformed.db"
    db_path.write_bytes(b"not sqlite")

    # When / Then
    with pytest.raises(DatabaseSchemaError):
        list_admin_accounts(str(db_path))


def test_incomplete_schema_is_rejected(tmp_path: Path) -> None:
    # Given
    db_path = tmp_path / "incomplete.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, "
            "password_hash TEXT, role TEXT)"
        )

    # When / Then
    with pytest.raises(DatabaseSchemaError):
        reset_admin_password(str(db_path), None, "new-password")


@pytest.mark.parametrize("new_password", ["12345", "x" * 129])
def test_reset_rejects_password_outside_service_boundary(
    tmp_path: Path, new_password: str
) -> None:
    # Given
    db_path = _initialized_db(tmp_path)
    _create_user(db_path, "admin", "before-reset")

    # When / Then
    with pytest.raises(InvalidPasswordError):
        reset_admin_password(db_path, None, new_password)


@pytest.mark.parametrize("new_password", ["123456", "x" * 128])
def test_reset_accepts_password_boundary_lengths(
    tmp_path: Path, new_password: str
) -> None:
    # Given
    db_path = _initialized_db(tmp_path)
    _create_user(db_path, "admin", "before-reset")

    # When
    reset_admin_password(db_path, None, new_password)

    # Then
    with get_db(db_path) as conn:
        password_hash = conn.execute(
            "SELECT password_hash FROM users WHERE username = 'admin'"
        ).fetchone()[0]
    assert verify_password(new_password, password_hash) is True


def test_reset_single_admin_replaces_hash_and_only_its_sessions(
    tmp_path: Path,
) -> None:
    # Given
    db_path = _initialized_db(tmp_path)
    admin_id = _create_user(db_path, "admin", "before-reset")
    member_id = _create_user(db_path, "member", "member-password", role="user")
    _create_session(db_path, "admin-session", admin_id)
    _create_session(db_path, "member-session", member_id)

    # When
    account = reset_admin_password(db_path, None, "after-reset")

    # Then
    with get_db(db_path) as conn:
        password_hash = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?", (admin_id,)
        ).fetchone()[0]
        tokens = [row[0] for row in conn.execute("SELECT token FROM sessions")]
    assert account.username == "admin"
    assert verify_password("before-reset", password_hash) is False
    assert verify_password("after-reset", password_hash) is True
    assert tokens == ["member-session"]


def test_reset_requires_username_when_multiple_admins(tmp_path: Path) -> None:
    # Given
    db_path = _initialized_db(tmp_path)
    _create_user(db_path, "first", "before-reset")
    _create_user(db_path, "second", "before-reset")

    # When / Then
    with pytest.raises(AdminSelectionRequiredError) as error:
        reset_admin_password(db_path, None, "after-reset")
    assert error.value.usernames == ("first", "second")


def test_reset_explicitly_selects_one_of_multiple_admins(tmp_path: Path) -> None:
    # Given
    db_path = _initialized_db(tmp_path)
    _create_user(db_path, "first", "first-password")
    _create_user(db_path, "second", "second-password")

    # When
    reset_admin_password(db_path, "second", "after-reset")

    # Then
    with get_db(db_path) as conn:
        rows = dict(conn.execute("SELECT username, password_hash FROM users"))
    assert verify_password("first-password", rows["first"]) is True
    assert verify_password("after-reset", rows["second"]) is True


def test_reset_rejects_database_without_admin(tmp_path: Path) -> None:
    # Given
    db_path = _initialized_db(tmp_path)
    _create_user(db_path, "member", "member-password", role="user")

    # When / Then
    with pytest.raises(AdminNotFoundError):
        reset_admin_password(db_path, None, "after-reset")


def test_reset_distinguishes_non_admin_username(tmp_path: Path) -> None:
    # Given
    db_path = _initialized_db(tmp_path)
    _create_user(db_path, "member", "member-password", role="user")

    # When / Then
    with pytest.raises(NotAdministratorError):
        reset_admin_password(db_path, "member", "after-reset")


def test_reset_reports_unknown_explicit_username(tmp_path: Path) -> None:
    # Given
    db_path = _initialized_db(tmp_path)
    _create_user(db_path, "admin", "before-reset")

    # When / Then
    with pytest.raises(AdminNotFoundError):
        reset_admin_password(db_path, "unknown", "after-reset")


def test_reset_rolls_back_hash_when_session_deletion_fails(tmp_path: Path) -> None:
    # Given
    db_path = _initialized_db(tmp_path)
    admin_id = _create_user(db_path, "admin", "before-reset")
    _create_session(db_path, "admin-session", admin_id)
    with get_db(db_path) as conn:
        conn.execute(
            "CREATE TRIGGER block_session_delete BEFORE DELETE ON sessions "
            "BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
        )
        conn.commit()

    # When / Then
    with pytest.raises(DatabaseOperationError):
        reset_admin_password(db_path, None, "after-reset")
    with get_db(db_path) as conn:
        password_hash = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?", (admin_id,)
        ).fetchone()[0]
        session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    assert verify_password("before-reset", password_hash) is True
    assert session_count == 1


def test_reset_rechecks_role_after_listed_account_becomes_stale(
    tmp_path: Path,
) -> None:
    # Given
    db_path = _initialized_db(tmp_path)
    _create_user(db_path, "admin", "before-reset")
    assert list_admin_accounts(db_path)[0].username == "admin"
    with get_db(db_path) as conn:
        conn.execute("UPDATE users SET role = 'user' WHERE username = 'admin'")
        conn.commit()

    # When / Then
    with pytest.raises(NotAdministratorError):
        reset_admin_password(db_path, "admin", "after-reset")
