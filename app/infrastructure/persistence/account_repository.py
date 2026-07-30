"""Legacy ``users`` table access for account-facing application code."""

from __future__ import annotations

import sqlite3
from typing import Final, NamedTuple, Optional, Union

SqlParameter = Union[int, str, None]


class LegacyAccount(NamedTuple):
    """Account projection backed by the current legacy ``users`` table."""

    user_id: int
    username: str
    password_hash: str
    role: str
    created_at: Optional[str]
    updated_at: Optional[str]
    nickname: Optional[str]
    avatar_color: int
    avatar_kind: str
    avatar_path: Optional[str]
    gender: Optional[str]
    birth_date: Optional[str]
    presence: str
    last_seen_at: Optional[str]
    default_landing_page: str
    theme_key: str
    elfie_limit: Optional[int]
    elfie_count: int


class AccountProfileUpdate(NamedTuple):
    """Explicit profile fields selected by the authenticated HTTP boundary."""

    update_nickname: bool
    nickname: Optional[str]
    update_avatar_color: bool
    avatar_color: Optional[int]
    update_avatar_kind: bool
    avatar_kind: Optional[str]


class AccountRepositoryWriteError(RuntimeError):
    """The legacy account table did not return an expected write result."""


_ACCOUNT_SELECT: Final[str] = """
    SELECT u.id, u.username, u.password_hash, u.role, u.created_at, u.updated_at,
           u.nickname, u.avatar_color, u.avatar_kind, u.avatar_path,
           u.gender, u.birth_date, u.presence, u.last_seen_at,
           u.default_landing_page, u.theme_key, u.elfie_limit,
           (SELECT COUNT(*) FROM elfie_registry
            WHERE owner_user_id = u.id) AS elfie_count
    FROM users u
"""


class AccountRepository:
    """Centralize account reads and writes while the legacy schema remains active."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def find_by_id(self, user_id: int) -> Optional[LegacyAccount]:
        row = self._connection.execute(
            f"{_ACCOUNT_SELECT} WHERE u.id = ?", (user_id,)
        ).fetchone()
        return None if row is None else _account_from_row(row)

    def find_by_username(self, username: str) -> Optional[LegacyAccount]:
        row = self._connection.execute(
            f"{_ACCOUNT_SELECT} WHERE u.username = ?", (username,)
        ).fetchone()
        return None if row is None else _account_from_row(row)

    def find_owner(self) -> Optional[LegacyAccount]:
        row = self._connection.execute(
            f"{_ACCOUNT_SELECT} WHERE u.role = 'owner' ORDER BY u.id LIMIT 1"
        ).fetchone()
        return None if row is None else _account_from_row(row)

    def list_excluding(self, user_id: int) -> tuple[LegacyAccount, ...]:
        rows = self._connection.execute(
            f"{_ACCOUNT_SELECT} WHERE u.id != ? ORDER BY u.id", (user_id,)
        ).fetchall()
        return tuple(_account_from_row(row) for row in rows)

    def username_exists(
        self, username: str, excluding_user_id: Optional[int] = None
    ) -> bool:
        if excluding_user_id is None:
            row = self._connection.execute(
                "SELECT 1 FROM users WHERE username = ?", (username,)
            ).fetchone()
        else:
            row = self._connection.execute(
                "SELECT 1 FROM users WHERE username = ? AND id != ?",
                (username, excluding_user_id),
            ).fetchone()
        return row is not None

    def has_any_account(self) -> bool:
        row = self._connection.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        return row is not None

    def create_owner(
        self,
        username: str,
        password_hash: str,
        nickname: str,
        avatar_color: int,
    ) -> int:
        cursor = self._connection.execute(
            """INSERT INTO users
               (username, password_hash, role, nickname, avatar_color, avatar_kind)
               VALUES (?, ?, 'owner', ?, ?, 'initials')""",
            (username, password_hash, nickname, avatar_color),
        )
        if cursor.lastrowid is None:
            raise AccountRepositoryWriteError(
                "legacy Owner insert did not return an account id"
            )
        return int(cursor.lastrowid)

    def create_user(self, username: str, password_hash: str) -> int:
        cursor = self._connection.execute(
            """INSERT INTO users
               (username, password_hash, role, presence, last_seen_at)
               VALUES (?, ?, 'user', 'offline', CURRENT_TIMESTAMP)""",
            (username, password_hash),
        )
        if cursor.lastrowid is None:
            raise AccountRepositoryWriteError(
                "legacy users insert did not return an account id"
            )
        return int(cursor.lastrowid)

    def update_profile(self, user_id: int, update: AccountProfileUpdate) -> None:
        assignments: list[str] = []
        parameters: list[SqlParameter] = []
        if update.update_nickname:
            assignments.append("nickname = ?")
            parameters.append(update.nickname)
        if update.update_avatar_color:
            assignments.append("avatar_color = ?")
            parameters.append(update.avatar_color)
        if update.update_avatar_kind:
            assignments.append("avatar_kind = ?")
            parameters.append(update.avatar_kind)
        if not assignments:
            return
        parameters.append(user_id)
        self._connection.execute(
            f"UPDATE users SET {', '.join(assignments)} WHERE id = ?", parameters
        )

    def update_password(self, user_id: int, password_hash: str) -> None:
        self._connection.execute(
            "UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (password_hash, user_id),
        )

    def update_theme(self, user_id: int, theme_key: str) -> None:
        self._connection.execute(
            "UPDATE users SET theme_key = ? WHERE id = ?", (theme_key, user_id)
        )

    def update_avatar_path(self, user_id: int, avatar_path: str) -> None:
        self._connection.execute(
            "UPDATE users SET avatar_path = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (avatar_path, user_id),
        )

    def update_quota(self, user_id: int, quota: Optional[int]) -> None:
        self._connection.execute(
            "UPDATE users SET elfie_limit = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (quota, user_id),
        )

    def recover_owner_credentials(
        self,
        user_id: int,
        username: str,
        password_hash: str,
        updated_at: str,
    ) -> None:
        self._connection.execute(
            "UPDATE users SET username = ?, password_hash = ?, updated_at = ? "
            "WHERE id = ? AND role = 'owner'",
            (username, password_hash, updated_at, user_id),
        )

    def delete(self, user_id: int) -> None:
        self._connection.execute("DELETE FROM users WHERE id = ?", (user_id,))


def _account_from_row(row: sqlite3.Row) -> LegacyAccount:
    quota = row["elfie_limit"]
    created_at = row["created_at"]
    updated_at = row["updated_at"]
    nickname = row["nickname"]
    avatar_path = row["avatar_path"]
    gender = row["gender"]
    birth_date = row["birth_date"]
    last_seen_at = row["last_seen_at"]
    return LegacyAccount(
        user_id=int(row["id"]),
        username=str(row["username"]),
        password_hash=str(row["password_hash"]),
        role=str(row["role"]),
        created_at=None if created_at is None else str(created_at),
        updated_at=None if updated_at is None else str(updated_at),
        nickname=None if nickname is None else str(nickname),
        avatar_color=int(row["avatar_color"]),
        avatar_kind=str(row["avatar_kind"]),
        avatar_path=None if avatar_path is None else str(avatar_path),
        gender=None if gender is None else str(gender),
        birth_date=None if birth_date is None else str(birth_date),
        presence=str(row["presence"]),
        last_seen_at=None if last_seen_at is None else str(last_seen_at),
        default_landing_page=str(row["default_landing_page"]),
        theme_key=str(row["theme_key"]),
        elfie_limit=None if quota is None else int(quota),
        elfie_count=int(row["elfie_count"]),
    )
