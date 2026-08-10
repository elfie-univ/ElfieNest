"""Transaction-scoped SQLite access for remaining account bootstrap callers."""

from __future__ import annotations

import sqlite3
from typing import Final, NamedTuple

ACCOUNT_ID_MIN_LENGTH: Final = 3
ACCOUNT_ID_MAX_LENGTH: Final = 32
DISPLAY_NAME_MAX_LENGTH: Final = 64
GENDER_VALUES: Final = frozenset(("male", "female"))


class AccountRecord(NamedTuple):
    """Final account projection without exposing schema-specific row objects."""

    user_id: int
    account_id: str
    password_hash: str
    role: str
    created_at: str
    updated_at: str
    display_name: str | None
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
    language: str


class AccountSummary(NamedTuple):
    """Canonical account identity returned by repository list queries."""

    user_id: int
    account_id: str
    display_name: str | None


class AccountRepositoryWriteError(RuntimeError):
    """An account insert did not return its generated identifier."""


class AccountRepositoryError(RuntimeError):
    """A final account read or write failed at the SQLite boundary."""


class AccountConflictError(AccountRepositoryError):
    """A final account write violates a uniqueness constraint."""


class AccountValidationError(AccountConflictError):
    """A final account value violates repository boundary validation."""


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

    def find_by_account_id(self, account_id: str) -> AccountRecord | None:
        normalized_account_id = _normalize_account_id(account_id)
        row = self._connection.execute(
            f"{_ACCOUNT_SELECT} WHERE account_id=?", (normalized_account_id,)
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

    def account_id_exists(self, account_id: str, excluding_user_id: int) -> bool:
        normalized_account_id = _normalize_account_id(account_id)
        try:
            row = self._connection.execute(
                "SELECT 1 FROM users WHERE account_id=? AND id!=?",
                (normalized_account_id, excluding_user_id),
            ).fetchone()
        except sqlite3.DatabaseError as error:
            raise AccountRepositoryError(str(error)) from error
        return row is not None

    def create_owner(
        self,
        *,
        account_id: str,
        password_hash: str,
        display_name: str | None,
        avatar_color: int,
    ) -> int:
        normalized_account_id = _normalize_account_id(account_id)
        normalized_display_name = _normalize_display_name(display_name)
        try:
            cursor = self._connection.execute(
                """INSERT INTO users
                   (account_id,password_hash,role,display_name,avatar_color,avatar_kind)
                   VALUES (?,?,'owner',?,?,'initials')""",
                (
                    normalized_account_id,
                    password_hash,
                    normalized_display_name,
                    avatar_color,
                ),
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
        account_id: str,
        password_hash: str,
        updated_at: str,
    ) -> None:
        normalized_account_id = _normalize_account_id(account_id)
        try:
            self._connection.execute(
                "UPDATE users SET account_id=?,password_hash=?,updated_at=? "
                "WHERE id=? AND role='owner'",
                (normalized_account_id, password_hash, updated_at, user_id),
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

    def update_profile(
        self,
        user_id: int,
        *,
        account_id: str,
        display_name: str | None,
        avatar_color: int,
        avatar_kind: str,
        gender: str,
        birth_date: str | None,
    ) -> None:
        """Replace the editable identity projection in one guarded write."""
        normalized_account_id = _normalize_account_id(account_id)
        normalized_display_name = _normalize_display_name(display_name)
        normalized_gender = _normalize_gender(gender)
        if self.account_id_exists(normalized_account_id, excluding_user_id=user_id):
            raise AccountConflictError("account_id already exists")
        try:
            self._connection.execute(
                """UPDATE users SET account_id=?,display_name=?,avatar_color=?,
                   avatar_kind=?,gender=?,birth_date=?,updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (
                    normalized_account_id,
                    normalized_display_name,
                    avatar_color,
                    avatar_kind,
                    normalized_gender,
                    birth_date,
                    user_id,
                ),
            )
        except sqlite3.IntegrityError as error:
            raise AccountConflictError(str(error)) from error
        except sqlite3.DatabaseError as error:
            raise AccountRepositoryError(str(error)) from error

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

    def list_non_owner_users(self) -> list[AccountSummary]:
        """List all non-owner users with their basic profile."""
        rows = self._connection.execute(
            "SELECT id, account_id, display_name FROM users WHERE role = 'user' ORDER BY id"
        ).fetchall()
        return [
            AccountSummary(
                user_id=int(row["id"]),
                account_id=str(row["account_id"]),
                display_name=(
                    None if row["display_name"] is None else str(row["display_name"])
                ),
            )
            for row in rows
        ]


_ACCOUNT_SELECT = """
SELECT id,account_id,password_hash,role,created_at,updated_at,display_name,
       avatar_color,avatar_kind,avatar_path,gender,birth_date,presence,last_seen_at,
       default_landing_page,theme_key,elfie_limit,language
FROM users
"""


def _record_from_row(row: sqlite3.Row) -> AccountRecord:
    return AccountRecord(
        user_id=int(row["id"]),
        account_id=str(row["account_id"]),
        password_hash=str(row["password_hash"]),
        role=str(row["role"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        display_name=None if row["display_name"] is None else str(row["display_name"]),
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
        language=str(row["language"]),
    )


def _normalize_account_id(account_id: str) -> str:
    normalized = account_id.strip()
    if not ACCOUNT_ID_MIN_LENGTH <= len(normalized) <= ACCOUNT_ID_MAX_LENGTH:
        raise AccountValidationError("account_id must be 3-32 characters after trim")
    return normalized


def _normalize_display_name(display_name: str | None) -> str | None:
    if display_name is None:
        return None
    normalized = display_name.strip()
    if normalized == "":
        return None
    if len(normalized) > DISPLAY_NAME_MAX_LENGTH:
        raise AccountValidationError("display_name must be at most 64 characters")
    return normalized


def _normalize_gender(gender: str) -> str:
    normalized = gender.strip().lower()
    if normalized not in GENDER_VALUES:
        raise AccountValidationError("gender must be male or female")
    return normalized
