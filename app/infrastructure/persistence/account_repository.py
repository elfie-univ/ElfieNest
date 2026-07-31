"""Final ``users`` table access for account-facing application code."""

from __future__ import annotations

import sqlite3
from typing import NamedTuple


class AccountRecord(NamedTuple):
    """Final account projection without exposing schema-specific row objects."""

    user_id: int
    username: str
    password_hash: str
    role: str
    created_at: str
    updated_at: str
    nickname: str | None
    avatar_color: int
    avatar_kind: str
    avatar_path: str | None
    gender: str | None
    birth_date: str | None
    presence: str
    last_seen_at: str | None
    default_landing_page: str
    theme_key: str
    elfie_limit: int | None


class AccountRepositoryWriteError(RuntimeError):
    """An account insert did not return its generated identifier."""


class AccountRepositoryError(RuntimeError):
    """A final account read or write failed at the SQLite boundary."""


class AccountConflictError(AccountRepositoryError):
    """A final account write violates a uniqueness constraint."""


class AccountRepository:
    """Own final account reads and writes on one caller-managed transaction."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def begin_immediate(self) -> None:
        """Open the write transaction used by account orchestration."""
        try:
            self._connection.execute("BEGIN IMMEDIATE")
        except sqlite3.DatabaseError as error:
            raise AccountRepositoryError(str(error)) from error

    def find_owner(self) -> AccountRecord | None:
        try:
            row = self._connection.execute(
                f"{_ACCOUNT_SELECT} WHERE role='owner' ORDER BY id LIMIT 1"
            ).fetchone()
        except sqlite3.DatabaseError as error:
            raise AccountRepositoryError(str(error)) from error
        return None if row is None else _record_from_row(row)

    def find_by_username(self, username: str) -> AccountRecord | None:
        row = self._connection.execute(
            f"{_ACCOUNT_SELECT} WHERE username=?", (username,)
        ).fetchone()
        return None if row is None else _record_from_row(row)

    def has_any_account(self) -> bool:
        try:
            row = self._connection.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        except sqlite3.DatabaseError as error:
            raise AccountRepositoryError(str(error)) from error
        return row is not None

    def elfie_limit(self, user_id: int, default: int) -> int | None:
        """Return the effective final limit, or ``None`` for an absent user."""
        try:
            row = self._connection.execute(
                "SELECT elfie_limit FROM users WHERE id=?", (user_id,)
            ).fetchone()
        except sqlite3.DatabaseError as error:
            raise AccountRepositoryError(str(error)) from error
        if row is None:
            return None
        return default if row[0] is None else int(row[0])

    def username_exists(self, username: str, excluding_user_id: int) -> bool:
        try:
            row = self._connection.execute(
                "SELECT 1 FROM users WHERE username=? AND id!=?",
                (username, excluding_user_id),
            ).fetchone()
        except sqlite3.DatabaseError as error:
            raise AccountRepositoryError(str(error)) from error
        return row is not None

    def create_owner(
        self,
        *,
        username: str,
        password_hash: str,
        nickname: str,
        avatar_color: int,
    ) -> int:
        try:
            cursor = self._connection.execute(
                """INSERT INTO users
                   (username,password_hash,role,nickname,avatar_color,avatar_kind)
                   VALUES (?,?,'owner',?,?,'initials')""",
                (username, password_hash, nickname, avatar_color),
            )
        except sqlite3.IntegrityError as error:
            raise AccountConflictError(str(error)) from error
        except sqlite3.DatabaseError as error:
            raise AccountRepositoryError(str(error)) from error
        if cursor.lastrowid is None:
            raise AccountRepositoryWriteError("Owner insert returned no user id")
        return int(cursor.lastrowid)

    def recover_owner_credentials(
        self,
        user_id: int,
        username: str,
        password_hash: str,
        updated_at: str,
    ) -> None:
        try:
            self._connection.execute(
                "UPDATE users SET username=?,password_hash=?,updated_at=? "
                "WHERE id=? AND role='owner'",
                (username, password_hash, updated_at, user_id),
            )
        except sqlite3.IntegrityError as error:
            raise AccountConflictError(str(error)) from error
        except sqlite3.DatabaseError as error:
            raise AccountRepositoryError(str(error)) from error

    def update_avatar_path(self, user_id: int, avatar_path: str | None) -> None:
        self._connection.execute(
            "UPDATE users SET avatar_path=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (avatar_path, user_id),
        )

    def update_quota(self, user_id: int, quota: int | None) -> None:
        self._connection.execute(
            "UPDATE users SET elfie_limit=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (quota, user_id),
        )

    def update_theme(self, user_id: int, theme_key: str) -> None:
        self._connection.execute(
            "UPDATE users SET theme_key = ?,updated_at=CURRENT_TIMESTAMP WHERE id = ?",
            (theme_key, user_id),
        )

    def list_non_owner_users(self) -> list[sqlite3.Row]:
        """List all non-owner users with their basic profile."""
        return self._connection.execute(
            "SELECT id, username, nickname FROM users WHERE role = 'user' ORDER BY id"
        ).fetchall()


_ACCOUNT_SELECT = """
SELECT id,username,password_hash,role,created_at,updated_at,nickname,
       avatar_color,avatar_kind,avatar_path,gender,birth_date,presence,last_seen_at,
       default_landing_page,theme_key,elfie_limit
FROM users
"""


def _record_from_row(row: sqlite3.Row) -> AccountRecord:
    return AccountRecord(
        user_id=int(row["id"]),
        username=str(row["username"]),
        password_hash=str(row["password_hash"]),
        role=str(row["role"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        nickname=None if row["nickname"] is None else str(row["nickname"]),
        avatar_color=int(row["avatar_color"]),
        avatar_kind=str(row["avatar_kind"]),
        avatar_path=None if row["avatar_path"] is None else str(row["avatar_path"]),
        gender=None if row["gender"] is None else str(row["gender"]),
        birth_date=None if row["birth_date"] is None else str(row["birth_date"]),
        presence=str(row["presence"]),
        last_seen_at=None if row["last_seen_at"] is None else str(row["last_seen_at"]),
        default_landing_page=str(row["default_landing_page"]),
        theme_key=str(row["theme_key"]),
        elfie_limit=None if row["elfie_limit"] is None else int(row["elfie_limit"]),
    )
