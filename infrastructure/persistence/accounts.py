"""SQLite implementation of the Accounts credential and session Port."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import NamedTuple

from app.features.accounts import (
    AccountCredentials,
    AccountPrincipal,
    parse_account_role,
)

from .sqlite_connection import app_sqlite_connection


class SessionPrincipal(NamedTuple):
    user_id: int
    account_id: str
    role: str
    default_landing_page: str


class ActiveSessionRecord(NamedTuple):
    token_hash: str
    account_id: str
    expires_at: str


def hash_session_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class SessionRepository:
    """Transaction-scoped session persistence used by remaining admin slices."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def issue(self, user_id: int, expires_at: datetime) -> str:
        raw_token = secrets.token_hex(32)
        self._connection.execute(
            "INSERT INTO sessions (token_hash,user_id,expires_at) VALUES (?,?,?)",
            (hash_session_token(raw_token), user_id, _utc_text(expires_at)),
        )
        return raw_token

    def find_active(self, raw_token: str, now: datetime) -> SessionPrincipal | None:
        if not raw_token:
            return None
        row = self._connection.execute(
            """SELECT users.id,users.account_id,users.role,users.default_landing_page
               FROM sessions JOIN users ON sessions.user_id=users.id
               WHERE sessions.token_hash=? AND sessions.revoked_at IS NULL
                 AND sessions.expires_at>?""",
            (hash_session_token(raw_token), _utc_text(now)),
        ).fetchone()
        if row is None:
            return None
        return SessionPrincipal(
            user_id=int(row["id"]),
            account_id=str(row["account_id"]),
            role=str(row["role"]),
            default_landing_page=str(row["default_landing_page"]),
        )

    def revoke(self, raw_token: str, revoked_at: datetime) -> None:
        if raw_token:
            self._connection.execute(
                "UPDATE sessions SET revoked_at=COALESCE(revoked_at,?) "
                "WHERE token_hash=?",
                (_utc_text(revoked_at), hash_session_token(raw_token)),
            )

    def revoke_for_user(self, user_id: int, revoked_at: datetime) -> None:
        self._connection.execute(
            "UPDATE sessions SET revoked_at=COALESCE(revoked_at,?) WHERE user_id=?",
            (_utc_text(revoked_at), user_id),
        )

    def count_active(self, now: datetime) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) FROM sessions WHERE revoked_at IS NULL AND expires_at>?",
            (_utc_text(now),),
        ).fetchone()
        return 0 if row is None else int(row[0])

    def list_active(self, now: datetime, limit: int) -> tuple[ActiveSessionRecord, ...]:
        rows = self._connection.execute(
            """SELECT sessions.token_hash,users.account_id,sessions.expires_at
               FROM sessions JOIN users ON sessions.user_id=users.id
               WHERE sessions.revoked_at IS NULL AND sessions.expires_at>?
               ORDER BY sessions.expires_at DESC LIMIT ?""",
            (_utc_text(now), limit),
        ).fetchall()
        return tuple(
            ActiveSessionRecord(
                token_hash=str(row["token_hash"]),
                account_id=str(row["account_id"]),
                expires_at=str(row["expires_at"]),
            )
            for row in rows
        )


class SQLiteAccountsAdapter:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def find_credentials(self, account_id: str) -> AccountCredentials | None:
        with app_sqlite_connection(self._db_path) as connection:
            row = connection.execute(
                """SELECT id,account_id,password_hash,role,display_name,
                          default_landing_page
                   FROM users WHERE account_id=?""",
                (account_id,),
            ).fetchone()
        if row is None:
            return None
        return AccountCredentials(
            user_id=int(row["id"]),
            account_id=str(row["account_id"]),
            password_hash=str(row["password_hash"]),
            role=str(row["role"]),
            display_name=(
                None if row["display_name"] is None else str(row["display_name"])
            ),
            default_landing_page=str(row["default_landing_page"]),
        )

    def issue_session(self, user_id: int, expires_at: datetime) -> str:
        with app_sqlite_connection(self._db_path) as connection:
            token = SessionRepository(connection).issue(user_id, expires_at)
            connection.commit()
        return token

    def find_session(
        self, raw_token: str, now: datetime
    ) -> AccountPrincipal | None:
        with app_sqlite_connection(self._db_path) as connection:
            record = SessionRepository(connection).find_active(raw_token, now)
        if record is None:
            return None
        return AccountPrincipal(
            user_id=record.user_id,
            account_id=record.account_id,
            role=parse_account_role(record.role),
            default_landing_page=record.default_landing_page,
        )

    def revoke_session(self, raw_token: str, revoked_at: datetime) -> None:
        with app_sqlite_connection(self._db_path) as connection:
            SessionRepository(connection).revoke(raw_token, revoked_at)
            connection.commit()


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


__all__ = ("SessionRepository", "SQLiteAccountsAdapter", "hash_session_token")
