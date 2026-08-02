"""SHA-256-only persistence for final Web sessions."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import NamedTuple


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
    """Return the irreversible digest used as the final session key."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class SessionRepository:
    """Issue and revoke final sessions while callers retain raw cookie tokens."""

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


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")
