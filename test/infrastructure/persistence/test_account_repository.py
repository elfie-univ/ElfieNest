from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from infrastructure.persistence.account_repository import (
    AccountConflictError,
    AccountRepository,
    AccountValidationError,
)
from infrastructure.persistence.final_schema import create_final_nest_database
from infrastructure.persistence.sqlite_connection import app_sqlite_connection


def test_final_account_projection_preserves_profile_fields(tmp_path: Path) -> None:
    # Given: a fresh final database and an owner created through the repository.
    db_path = _create_database(tmp_path)
    with app_sqlite_connection(db_path) as connection:
        repository = AccountRepository(connection)
        user_id = repository.create_owner(
            account_id=" owner01 ",
            password_hash="password-hash",
            display_name=" Owner Name ",
            avatar_color=7,
        )
        repository.update_avatar_path(user_id, "assets/users/1/avatar.png")
        repository.update_quota(user_id, 12)
        repository.update_theme(user_id, "harbor-blue")
        connection.commit()

    # When: the owner row is projected back into an AccountRecord.
    with app_sqlite_connection(db_path) as connection:
        account = AccountRepository(connection).find_owner()

    # Then: canonical account fields and profile defaults round-trip exactly.
    assert account is not None
    assert account.user_id == user_id
    assert account.account_id == "owner01"
    assert account.display_name == "Owner Name"
    assert account.avatar_color == 7
    assert account.avatar_kind == "initials"
    assert account.avatar_path == "assets/users/1/avatar.png"
    assert account.elfie_limit == 12
    assert account.theme_key == "harbor-blue"
    assert account.language == "zh-CN"


def test_final_account_projection_normalizes_empty_display_name(
    tmp_path: Path,
) -> None:
    # Given: an owner created with whitespace-only display name.
    db_path = _create_database(tmp_path)
    with app_sqlite_connection(db_path) as connection:
        AccountRepository(connection).create_owner(
            account_id="owner01",
            password_hash="password-hash",
            display_name="  ",
            avatar_color=0,
        )
        connection.commit()

    # When: the owner row is read back.
    with app_sqlite_connection(db_path) as connection:
        account = AccountRepository(connection).find_by_account_id(" owner01 ")

    # Then: the account ID lookup trims input and display_name is nullable.
    assert account is not None
    assert account.account_id == "owner01"
    assert account.display_name is None


def test_final_schema_rejects_second_owner(tmp_path: Path) -> None:
    # Given: an existing owner row.
    db_path = _create_database(tmp_path)
    with app_sqlite_connection(db_path) as connection:
        repository = AccountRepository(connection)
        repository.create_owner(
            account_id="owner01",
            password_hash="password-hash-one",
            display_name="One",
            avatar_color=0,
        )

        # When/Then: a second owner violates the final owner uniqueness rule.
        with pytest.raises(AccountConflictError):
            repository.create_owner(
                account_id="owner02",
                password_hash="password-hash-two",
                display_name="Two",
                avatar_color=1,
            )


def test_account_repository_rejects_malformed_account_values(
    tmp_path: Path,
) -> None:
    # Given: one fresh final database per malformed account input.
    for index, account_id in enumerate(("", "  ", "ab", "a" * 33)):
        db_path = _create_named_database(tmp_path, f"invalid-{index}")
        with app_sqlite_connection(db_path) as connection:
            repository = AccountRepository(connection)

            # When/Then: malformed account IDs fail before any owner row is created.
            with pytest.raises(AccountValidationError):
                repository.create_owner(
                    account_id=account_id,
                    password_hash="password-hash-two",
                    display_name="Member",
                    avatar_color=1,
                )

    # Given: a fresh final database for display-name boundary checks.
    db_path = _create_named_database(tmp_path, "overlong-display")
    with app_sqlite_connection(db_path) as connection:
        with pytest.raises(AccountValidationError):
            AccountRepository(connection).create_owner(
                account_id="member01",
                password_hash="password-hash-two",
                display_name="x" * 65,
                avatar_color=1,
            )

    # Given: an owner and a member account already exist.
    db_path = _create_named_database(tmp_path, "duplicate")
    with app_sqlite_connection(db_path) as connection:
        repository = AccountRepository(connection)
        owner_id = repository.create_owner(
            account_id="owner01",
            password_hash="password-hash-owner",
            display_name="Owner",
            avatar_color=1,
        )
        connection.execute(
            "INSERT INTO users(account_id,password_hash,role) VALUES(?,?,?)",
            ("member01", "password-hash-member", "user"),
        )

        # When/Then: duplicate account IDs fail after repository trimming.
        with pytest.raises(AccountConflictError):
            repository.recover_owner_credentials(
                owner_id,
                " member01 ",
                "password-hash-new",
                "2026-08-01T00:00:00Z",
            )


def test_account_repository_never_reads_legacy_columns(tmp_path: Path) -> None:
    # Given: a canonical final row inserted without any legacy account columns.
    db_path = _create_database(tmp_path)
    with app_sqlite_connection(db_path) as connection:
        connection.execute(
            "INSERT INTO users(account_id,display_name,password_hash,role) "
            "VALUES('owner01','Owner','password-hash','owner')"
        )
        connection.commit()

    # When: the repository builds AccountRecord from the row.
    with app_sqlite_connection(db_path) as connection:
        account = AccountRepository(connection).find_owner()
        with pytest.raises(sqlite3.OperationalError, match="no such column"):
            connection.execute("SELECT username FROM users").fetchone()
        with pytest.raises(sqlite3.OperationalError, match="no such column"):
            connection.execute("SELECT nickname FROM users").fetchone()

    # Then: row construction uses display_name and canonical identifiers only.
    assert account is not None
    assert account.user_id == 1
    assert account.account_id == "owner01"
    assert account.display_name == "Owner"


def test_account_repository_lists_typed_canonical_user_summaries(
    tmp_path: Path,
) -> None:
    db_path = _create_database(tmp_path)
    with app_sqlite_connection(db_path) as connection:
        connection.execute(
            "INSERT INTO users(account_id,display_name,password_hash,role) "
            "VALUES('member01','Member','password-hash','user')"
        )

        summaries = AccountRepository(connection).list_non_owner_users()

    assert len(summaries) == 1
    assert summaries[0].user_id == 1
    assert summaries[0].account_id == "member01"
    assert summaries[0].display_name == "Member"
    assert not hasattr(summaries[0], "id")


def _create_database(tmp_path: Path) -> Path:
    return create_final_nest_database(tmp_path / "nest.db")


def _create_named_database(tmp_path: Path, name: str) -> Path:
    directory = tmp_path / name
    directory.mkdir()
    return create_final_nest_database(directory / "nest.db")
