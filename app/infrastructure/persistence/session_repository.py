"""Hash-only Web session persistence for the Card 16 cutover."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from app.infrastructure.persistence.store import get_db
from app.infrastructure.persistence.transition_account_schema import (
    ensure_session_transition_schema,
)


@dataclass(frozen=True)
class SessionPrincipal:
    __slots__ = ("user_id", "username", "role", "default_landing_page")

    user_id: int
    username: str
    role: str
    default_landing_page: str


@dataclass(frozen=True)
class ActiveSessionRecord:
    __slots__ = ("token_hash", "username", "expires_at")

    token_hash: str
    username: str
    expires_at: str


def hash_session_token(raw_token: str) -> str:
    """Return the irreversible lowercase SHA-256 digest stored by SQLite."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class SessionRepository:
    """Persist and revalidate Web sessions without storing raw cookie tokens."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def ensure_schema(self) -> None:
        ensure_session_transition_schema(self._connection)

    def activate_cutover(self) -> None:
        """Create v2 and invalidate every legacy raw-token row without copying it."""
        self.ensure_schema()
        if self._legacy_table_exists():
            self._connection.execute("DELETE FROM sessions")

    def issue(self, user_id: int, expires_at: datetime) -> str:
        raw_token = secrets.token_hex(32)
        self.activate_cutover()
        self._connection.execute(
            "INSERT INTO sessions_v2 (token_hash, user_id, expires_at) "
            "VALUES (?, ?, ?)",
            (hash_session_token(raw_token), user_id, _utc_text(expires_at)),
        )
        return raw_token

    def find_active(
        self, raw_token: str, now: datetime
    ) -> SessionPrincipal | None:
        if not raw_token or not self._table_exists():
            return None
        row = self._connection.execute(
            """
            SELECT u.id, u.username, u.role, u.default_landing_page
            FROM sessions_v2 AS session
            JOIN users AS u ON session.user_id = u.id
            WHERE session.token_hash = ?
              AND session.revoked_at IS NULL
              AND session.expires_at > ?
            """,
            (hash_session_token(raw_token), _utc_text(now)),
        ).fetchone()
        if row is None:
            return None
        return SessionPrincipal(
            user_id=int(row["id"]),
            username=str(row["username"]),
            role=str(row["role"]),
            default_landing_page=str(row["default_landing_page"]),
        )

    def revoke(self, raw_token: str, revoked_at: datetime) -> None:
        if not raw_token or not self._table_exists():
            return
        self._connection.execute(
            "UPDATE sessions_v2 SET revoked_at = COALESCE(revoked_at, ?) "
            "WHERE token_hash = ?",
            (_utc_text(revoked_at), hash_session_token(raw_token)),
        )

    def revoke_for_user(
        self,
        user_id: int,
        revoked_at: datetime,
        except_raw_token: str | None = None,
    ) -> None:
        if not self._table_exists():
            return
        parameters: tuple[str, int] | tuple[str, int, str]
        statement = (
            "UPDATE sessions_v2 SET revoked_at = COALESCE(revoked_at, ?) "
            "WHERE user_id = ?"
        )
        if except_raw_token is None:
            parameters = (_utc_text(revoked_at), user_id)
        else:
            statement += " AND token_hash != ?"
            parameters = (
                _utc_text(revoked_at),
                user_id,
                hash_session_token(except_raw_token),
            )
        self._connection.execute(statement, parameters)

    def delete_for_user(self, user_id: int) -> None:
        if self._table_exists():
            self._connection.execute(
                "DELETE FROM sessions_v2 WHERE user_id = ?", (user_id,)
            )

    def count_active(self, now: datetime) -> int:
        if not self._table_exists():
            return 0
        row = self._connection.execute(
            "SELECT COUNT(*) FROM sessions_v2 "
            "WHERE revoked_at IS NULL AND expires_at > ?",
            (_utc_text(now),),
        ).fetchone()
        return 0 if row is None else int(row[0])

    def list_active(
        self, now: datetime, limit: int
    ) -> tuple[ActiveSessionRecord, ...]:
        if not self._table_exists():
            return ()
        rows = self._connection.execute(
            """
            SELECT session.token_hash, u.username, session.expires_at
            FROM sessions_v2 AS session
            JOIN users AS u ON session.user_id = u.id
            WHERE session.revoked_at IS NULL AND session.expires_at > ?
            ORDER BY session.expires_at DESC
            LIMIT ?
            """,
            (_utc_text(now), limit),
        ).fetchall()
        return tuple(
            ActiveSessionRecord(
                token_hash=str(row["token_hash"]),
                username=str(row["username"]),
                expires_at=str(row["expires_at"]),
            )
            for row in rows
        )

    def _table_exists(self) -> bool:
        return (
            self._connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = 'sessions_v2'"
            ).fetchone()
            is not None
        )

    def _legacy_table_exists(self) -> bool:
        return (
            self._connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = 'sessions'"
            ).fetchone()
            is not None
        )


def activate_session_storage(db_path: str) -> None:
    """Atomically activate hash-only sessions and empty the legacy raw table."""
    with get_db(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        SessionRepository(connection).activate_cutover()
        connection.commit()


def revoke_other_sessions(
    connection: sqlite3.Connection,
    user_id: int,
    current_raw_token: str,
) -> None:
    """Revoke a user's other sessions inside the caller's password transaction."""
    SessionRepository(connection).revoke_for_user(
        user_id,
        datetime.now(timezone.utc),
        except_raw_token=current_raw_token,
    )


def _utc_text(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc)
    return normalized.isoformat(timespec="microseconds")
