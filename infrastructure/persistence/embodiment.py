"""SQLite adapter for one Elfie's optimistic, versioned embodiment lease."""

from __future__ import annotations

import sqlite3
import time
from typing import ContextManager

from app.orchestration.embodiment.models import EmbodimentSession
from app.orchestration.embodiment.ports import EmbodimentLeaseConflict
from nest.embodiment import EmbodimentState

from .sqlite_connection import app_sqlite_connection


def get_db(db_path: str) -> ContextManager[sqlite3.Connection]:
    """Keep the moved transaction implementation on the root SQLite boundary."""
    return app_sqlite_connection(db_path)


def get_embodiment_session(db_path: str, elfie_id: str) -> EmbodimentSession:
    """Read the current lease, defaulting a never-hosted Elfie to version zero."""
    with get_db(db_path) as connection:
        row = connection.execute(
            """SELECT state, body_id, lease_expires_at, lease_version
               FROM embodiment_sessions WHERE elfie_id=?""",
            (elfie_id,),
        ).fetchone()
    return _row_to_session(elfie_id, row)


def begin_hosting(
    db_path: str, elfie_id: str, body_id: str, *, lease_seconds: float
) -> EmbodimentSession:
    """Reserve an external body as lease version one."""
    if lease_seconds <= 0:
        raise ValueError("lease_seconds 必须为正数")
    expires_at = time.time() + lease_seconds
    with get_db(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        current = _read_session(connection, elfie_id)
        if current.state is not EmbodimentState.AT_NEST:
            connection.rollback()
            raise EmbodimentLeaseConflict(
                f"精灵 {elfie_id} 当前处于 {current.state.value}，不能再次托管"
            )
        state = current.state.transition_to(EmbodimentState.SWITCHING_TO_HOSTED)
        try:
            next_version = current.lease_version + 1
            if current.lease_version == 0:
                connection.execute(
                    """INSERT INTO embodiment_sessions(
                           elfie_id, body_id, state, lease_expires_at, lease_version
                       ) VALUES (?, ?, ?, ?, ?)""",
                    (elfie_id, body_id, state.value, expires_at, next_version),
                )
            else:
                cursor = connection.execute(
                    """UPDATE embodiment_sessions
                       SET body_id=?, state=?, lease_expires_at=?, lease_version=?,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE elfie_id=? AND lease_version=?""",
                    (
                        body_id,
                        state.value,
                        expires_at,
                        next_version,
                        elfie_id,
                        current.lease_version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise EmbodimentLeaseConflict("具身租约版本已过期")
            body_cursor = connection.execute(
                """UPDATE external_bodies
                   SET status='active', updated_at=CURRENT_TIMESTAMP
                   WHERE body_id=? AND status='available'""",
                (body_id,),
            )
            if body_cursor.rowcount != 1:
                raise EmbodimentLeaseConflict("外部身体当前不可用")
            connection.execute(
                """UPDATE elfies SET status='away', updated_at=CURRENT_TIMESTAMP
                   WHERE elfie_id=?""",
                (elfie_id,),
            )
        except sqlite3.IntegrityError as error:
            connection.rollback()
            raise EmbodimentLeaseConflict("外部身体不可用或不属于该精灵") from error
        connection.commit()
    return EmbodimentSession(elfie_id, state, body_id, expires_at, next_version)


def complete_hosting(
    db_path: str, elfie_id: str, lease_version: int
) -> EmbodimentSession:
    return _transition(db_path, elfie_id, lease_version, EmbodimentState.HOSTED)


def start_return(db_path: str, elfie_id: str, lease_version: int) -> EmbodimentSession:
    return _transition(
        db_path, elfie_id, lease_version, EmbodimentState.RETURNING_TO_NEST
    )


def complete_return(
    db_path: str, elfie_id: str, lease_version: int
) -> EmbodimentSession:
    return _transition(db_path, elfie_id, lease_version, EmbodimentState.AT_NEST)


def abort_hosting(db_path: str, elfie_id: str, lease_version: int) -> EmbodimentSession:
    return _transition(db_path, elfie_id, lease_version, EmbodimentState.AT_NEST)


def renew_hosting_heartbeat(
    db_path: str,
    elfie_id: str,
    lease_version: int,
    *,
    lease_seconds: float,
) -> EmbodimentSession:
    """Advance and extend a live hosted lease."""
    if lease_seconds <= 0:
        raise ValueError("lease_seconds 必须为正数")
    now = time.time()
    current = get_embodiment_session(db_path, elfie_id)
    if current.lease_version != lease_version:
        raise EmbodimentLeaseConflict("具身租约版本已过期")
    if current.state is not EmbodimentState.HOSTED:
        raise EmbodimentLeaseConflict("只有已托管会话可以续租心跳")
    if current.lease_expires_at is None or current.lease_expires_at <= now:
        _transition(db_path, elfie_id, lease_version, EmbodimentState.OFFLINE)
        raise EmbodimentLeaseConflict("具身会话心跳已过期")
    return _write_transition(
        db_path,
        current,
        EmbodimentState.HOSTED,
        current.body_id,
        now + lease_seconds,
    )


def expire_stale_lease(
    db_path: str, elfie_id: str, *, now: float | None = None
) -> EmbodimentSession:
    """Advance an expired active lease to offline."""
    current = get_embodiment_session(db_path, elfie_id)
    observed_at = time.time() if now is None else now
    active = current.state not in (EmbodimentState.AT_NEST, EmbodimentState.OFFLINE)
    expired = (
        current.lease_expires_at is not None and current.lease_expires_at <= observed_at
    )
    if active and expired:
        return _transition(
            db_path, elfie_id, current.lease_version, EmbodimentState.OFFLINE
        )
    return current


def recover_offline_session(
    db_path: str, elfie_id: str, lease_version: int
) -> EmbodimentSession:
    return _transition(db_path, elfie_id, lease_version, EmbodimentState.AT_NEST)


def _transition(
    db_path: str,
    elfie_id: str,
    lease_version: int,
    target: EmbodimentState,
) -> EmbodimentSession:
    current = get_embodiment_session(db_path, elfie_id)
    if current.lease_version != lease_version or lease_version == 0:
        raise EmbodimentLeaseConflict("具身租约版本已过期")
    state = current.state.transition_to(target)
    body_id = (
        None
        if state in (EmbodimentState.AT_NEST, EmbodimentState.OFFLINE)
        else current.body_id
    )
    expires_at = (
        None
        if state in (EmbodimentState.AT_NEST, EmbodimentState.OFFLINE)
        else current.lease_expires_at
    )
    return _write_transition(db_path, current, state, body_id, expires_at)


def _write_transition(
    db_path: str,
    current: EmbodimentSession,
    state: EmbodimentState,
    body_id: str | None,
    lease_expires_at: float | None,
) -> EmbodimentSession:
    next_version = current.lease_version + 1
    with get_db(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            """UPDATE embodiment_sessions
               SET state=?, body_id=?, lease_expires_at=?, lease_version=?,
                   updated_at=CURRENT_TIMESTAMP
               WHERE elfie_id=? AND lease_version=?""",
            (
                state.value,
                body_id,
                lease_expires_at,
                next_version,
                current.elfie_id,
                current.lease_version,
            ),
        )
        if cursor.rowcount != 1:
            connection.rollback()
            raise EmbodimentLeaseConflict("具身租约版本已过期")
        if body_id is None and current.body_id is not None:
            connection.execute(
                """UPDATE external_bodies
                   SET status='available', updated_at=CURRENT_TIMESTAMP
                   WHERE body_id=? AND status='active'""",
                (current.body_id,),
            )
        if state is EmbodimentState.AT_NEST:
            connection.execute(
                """UPDATE elfies SET status='online', updated_at=CURRENT_TIMESTAMP
                   WHERE elfie_id=?""",
                (current.elfie_id,),
            )
        elif state is EmbodimentState.OFFLINE:
            connection.execute(
                """UPDATE elfies SET status='offline', updated_at=CURRENT_TIMESTAMP
                   WHERE elfie_id=?""",
                (current.elfie_id,),
            )
        connection.commit()
    return EmbodimentSession(
        current.elfie_id, state, body_id, lease_expires_at, next_version
    )


def _read_session(connection: sqlite3.Connection, elfie_id: str) -> EmbodimentSession:
    row = connection.execute(
        """SELECT state, body_id, lease_expires_at, lease_version
           FROM embodiment_sessions WHERE elfie_id=?""",
        (elfie_id,),
    ).fetchone()
    return _row_to_session(elfie_id, row)


def _row_to_session(elfie_id: str, row: sqlite3.Row | None) -> EmbodimentSession:
    if row is None:
        return EmbodimentSession(elfie_id, EmbodimentState.AT_NEST, None, None, 0)
    expires_at = row["lease_expires_at"]
    return EmbodimentSession(
        elfie_id=elfie_id,
        state=EmbodimentState(str(row["state"])),
        body_id=None if row["body_id"] is None else str(row["body_id"]),
        lease_expires_at=None if expires_at is None else float(expires_at),
        lease_version=int(row["lease_version"]),
    )


class SQLiteEmbodimentLeaseAdapter:
    """Implement the App-owned lease Port over the authoritative Nest database."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def get(self, elfie_id: str) -> EmbodimentSession:
        return get_embodiment_session(self._db_path, elfie_id)

    def begin_hosting(
        self, elfie_id: str, body_id: str, *, lease_seconds: float
    ) -> EmbodimentSession:
        return begin_hosting(
            self._db_path,
            elfie_id,
            body_id,
            lease_seconds=lease_seconds,
        )

    def complete_hosting(self, elfie_id: str, lease_version: int) -> EmbodimentSession:
        return complete_hosting(self._db_path, elfie_id, lease_version)

    def abort_hosting(self, elfie_id: str, lease_version: int) -> EmbodimentSession:
        return abort_hosting(self._db_path, elfie_id, lease_version)

    def start_return(self, elfie_id: str, lease_version: int) -> EmbodimentSession:
        return start_return(self._db_path, elfie_id, lease_version)

    def complete_return(self, elfie_id: str, lease_version: int) -> EmbodimentSession:
        return complete_return(self._db_path, elfie_id, lease_version)

    def heartbeat(
        self, elfie_id: str, lease_version: int, *, lease_seconds: float
    ) -> EmbodimentSession:
        return renew_hosting_heartbeat(
            self._db_path,
            elfie_id,
            lease_version,
            lease_seconds=lease_seconds,
        )

    def expire(self, elfie_id: str, *, now: float | None = None) -> EmbodimentSession:
        return expire_stale_lease(self._db_path, elfie_id, now=now)

    def recover(self, elfie_id: str, lease_version: int) -> EmbodimentSession:
        return recover_offline_session(self._db_path, elfie_id, lease_version)


__all__ = ("SQLiteEmbodimentLeaseAdapter",)
