"""Transactional persistence for one Elfie's active embodiment lease."""

from __future__ import annotations

import time
from dataclasses import dataclass
from uuid import uuid4

from app.infrastructure.persistence.store import get_db
from nest.embodiment import EmbodimentState, EmbodimentTransitionError


class EmbodimentLeaseConflict(RuntimeError):
    """Raised when a second transition attempts to take an active Elfie lease."""


@dataclass(frozen=True)
class EmbodimentSession:
    elfie_id: str
    session_id: str | None
    state: EmbodimentState
    body_id: str | None
    lease_expires_at: float | None


def get_embodiment_session(db_path: str, elfie_id: str) -> EmbodimentSession:
    """Read a session, treating pre-migration/idle Elfies as at-nest."""
    with get_db(db_path) as connection:
        row = connection.execute(
            """SELECT session_id, state, body_id, lease_expires_at
               FROM embodiment_sessions WHERE elfie_id = ?""",
            (elfie_id,),
        ).fetchone()
    return _row_to_session(elfie_id, row)


def begin_hosting(
    db_path: str, elfie_id: str, body_id: str, *, lease_seconds: float
) -> EmbodimentSession:
    """Atomically reserve the only active lease before a body bind starts."""
    if lease_seconds <= 0:
        raise ValueError("lease_seconds 必须为正数")
    session_id = uuid4().hex
    lease_expires_at = time.time() + lease_seconds
    with get_db(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        current = _row_to_session(
            elfie_id,
            connection.execute(
                """SELECT session_id, state, body_id, lease_expires_at
                   FROM embodiment_sessions WHERE elfie_id = ?""",
                (elfie_id,),
            ).fetchone(),
        )
        if current.state is not EmbodimentState.AT_NEST:
            connection.rollback()
            raise EmbodimentLeaseConflict(
                f"精灵 {elfie_id} 当前处于 {current.state.value}，不能再次托管"
            )
        state = current.state.transition_to(EmbodimentState.SWITCHING_TO_HOSTED)
        connection.execute(
            """INSERT INTO embodiment_sessions
               (elfie_id, session_id, state, body_id, lease_expires_at, updated_at)
               VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(elfie_id) DO UPDATE SET
                 session_id=excluded.session_id, state=excluded.state,
                 body_id=excluded.body_id, lease_expires_at=excluded.lease_expires_at,
                 updated_at=CURRENT_TIMESTAMP""",
            (elfie_id, session_id, state.value, body_id, lease_expires_at),
        )
        connection.commit()
    return EmbodimentSession(elfie_id, session_id, state, body_id, lease_expires_at)


def complete_hosting(db_path: str, elfie_id: str, session_id: str) -> EmbodimentSession:
    """Mark a successfully connected host body as active for its existing lease."""
    return _transition(db_path, elfie_id, session_id, EmbodimentState.HOSTED)


def start_return(db_path: str, elfie_id: str, session_id: str) -> EmbodimentSession:
    """Begin return after the external body has been asked to disconnect."""
    return _transition(db_path, elfie_id, session_id, EmbodimentState.RETURNING_TO_NEST)


def complete_return(db_path: str, elfie_id: str, session_id: str) -> EmbodimentSession:
    """Release the body/lease after a successful return to the Nest."""
    return _transition(db_path, elfie_id, session_id, EmbodimentState.AT_NEST)


def abort_hosting(db_path: str, elfie_id: str, session_id: str) -> EmbodimentSession:
    """Release a lease when the body connection failed after reservation."""
    return _transition(db_path, elfie_id, session_id, EmbodimentState.AT_NEST)


def renew_hosting_heartbeat(
    db_path: str, elfie_id: str, session_id: str, *, lease_seconds: float
) -> EmbodimentSession:
    """Extend a live hosted session lease, refusing stale or non-hosted sessions."""
    if lease_seconds <= 0:
        raise ValueError("lease_seconds 必须为正数")
    now = time.time()
    with get_db(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        current = _row_to_session(
            elfie_id,
            connection.execute(
                """SELECT session_id, state, body_id, lease_expires_at
                   FROM embodiment_sessions WHERE elfie_id = ?""",
                (elfie_id,),
            ).fetchone(),
        )
        if current.session_id != session_id:
            connection.rollback()
            raise EmbodimentLeaseConflict("具身会话不存在或已被新的租约替换")
        if current.state is not EmbodimentState.HOSTED:
            connection.rollback()
            raise EmbodimentLeaseConflict("只有已托管会话可以续租心跳")
        if current.lease_expires_at is None or current.lease_expires_at <= now:
            _write_session(connection, current, EmbodimentState.OFFLINE, None, None)
            connection.commit()
            raise EmbodimentLeaseConflict("具身会话心跳已过期")
        lease_expires_at = now + lease_seconds
        _write_session(
            connection,
            current,
            EmbodimentState.HOSTED,
            current.body_id,
            lease_expires_at,
        )
        connection.commit()
    return EmbodimentSession(
        elfie_id, session_id, EmbodimentState.HOSTED, current.body_id, lease_expires_at
    )


def expire_stale_lease(
    db_path: str, elfie_id: str, *, now: float | None = None
) -> EmbodimentSession:
    """Release an expired active lease and make the session observably offline."""
    observed_at = time.time() if now is None else now
    with get_db(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        current = _row_to_session(
            elfie_id,
            connection.execute(
                """SELECT session_id, state, body_id, lease_expires_at
                   FROM embodiment_sessions WHERE elfie_id = ?""",
                (elfie_id,),
            ).fetchone(),
        )
        active = current.state not in (EmbodimentState.AT_NEST, EmbodimentState.OFFLINE)
        expired = (
            current.lease_expires_at is not None
            and current.lease_expires_at <= observed_at
        )
        if active and expired:
            _write_session(connection, current, EmbodimentState.OFFLINE, None, None)
            connection.commit()
            return EmbodimentSession(
                elfie_id,
                current.session_id,
                EmbodimentState.OFFLINE,
                None,
                None,
            )
        connection.commit()
    return current


def recover_offline_session(
    db_path: str, elfie_id: str, session_id: str
) -> EmbodimentSession:
    """Acknowledge an offline session and make the Elfie available at the Nest."""
    return _transition(db_path, elfie_id, session_id, EmbodimentState.AT_NEST)


def _transition(
    db_path: str, elfie_id: str, session_id: str, target: EmbodimentState
) -> EmbodimentSession:
    with get_db(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        current = _row_to_session(
            elfie_id,
            connection.execute(
                """SELECT session_id, state, body_id, lease_expires_at
                   FROM embodiment_sessions WHERE elfie_id = ?""",
                (elfie_id,),
            ).fetchone(),
        )
        if current.session_id != session_id:
            connection.rollback()
            raise EmbodimentLeaseConflict("具身会话不存在或已被新的租约替换")
        try:
            state = current.state.transition_to(target)
        except EmbodimentTransitionError:
            connection.rollback()
            raise
        body_id = (
            None
            if state in (EmbodimentState.AT_NEST, EmbodimentState.OFFLINE)
            else current.body_id
        )
        lease_expires_at = (
            None
            if state in (EmbodimentState.AT_NEST, EmbodimentState.OFFLINE)
            else current.lease_expires_at
        )
        _write_session(connection, current, state, body_id, lease_expires_at)
        connection.commit()
    return EmbodimentSession(elfie_id, session_id, state, body_id, lease_expires_at)


def _write_session(
    connection,
    session: EmbodimentSession,
    state: EmbodimentState,
    body_id: str | None,
    lease_expires_at: float | None,
) -> None:
    connection.execute(
        """UPDATE embodiment_sessions
           SET state = ?, body_id = ?, lease_expires_at = ?, updated_at = CURRENT_TIMESTAMP
           WHERE elfie_id = ?""",
        (state.value, body_id, lease_expires_at, session.elfie_id),
    )


def _row_to_session(elfie_id: str, row) -> EmbodimentSession:
    if row is None:
        return EmbodimentSession(elfie_id, None, EmbodimentState.AT_NEST, None, None)
    return EmbodimentSession(
        elfie_id=elfie_id,
        session_id=str(row["session_id"]) if row["session_id"] is not None else None,
        state=EmbodimentState(str(row["state"])),
        body_id=str(row["body_id"]) if row["body_id"] is not None else None,
        lease_expires_at=(
            float(row["lease_expires_at"])
            if row["lease_expires_at"] is not None
            else None
        ),
    )
