"""Coordinate the real Elfie body binding with durable lease transitions."""

from __future__ import annotations

from app.features.embodiment import (
    EmbodimentConflict,
    Hosted,
    HostingFailed,
    HostingResult,
)
from app.infrastructure.persistence.embodiment_sessions import (
    EmbodimentLeaseConflict,
    EmbodimentSession,
    abort_hosting,
    begin_hosting,
    complete_hosting,
    complete_return,
    expire_stale_lease,
    get_embodiment_session,
    recover_offline_session,
    renew_hosting_heartbeat,
    start_return,
)
from elfie import Elfie
from elfie.body import BodyPort
from nest.embodiment import EmbodimentState


class EmbodimentSessionService:
    """Keep durable lease state and an Elfie's sole active BodyPort aligned."""

    def __init__(self, *, db_path: str, nest_body_id: str) -> None:
        self._db_path = db_path
        self._nest_body_id = nest_body_id

    def host(
        self, elfie_id: str, elfie: Elfie, body: BodyPort, *, lease_seconds: float
    ) -> HostingResult:
        """Acquire first, then bind; release the durable lease if binding fails."""
        try:
            switching = begin_hosting(
                self._db_path, elfie_id, body.body_id, lease_seconds=lease_seconds
            )
        except EmbodimentLeaseConflict as error:
            current = get_embodiment_session(self._db_path, elfie_id)
            return EmbodimentConflict(state=current.state, reason=str(error))

        existing = elfie.body_registry.get(body.body_id)
        if existing is None:
            elfie.register_body(body)
        elif existing is not body:
            restored = abort_hosting(self._db_path, elfie_id, _require_session_id(switching))
            return HostingFailed(
                restored_state=restored.state,
                reason="body_id 已注册为另一个身体实例",
            )
        try:
            elfie.bind_body(body.body_id)
        except RuntimeError as error:
            restored = abort_hosting(self._db_path, elfie_id, _require_session_id(switching))
            return HostingFailed(restored_state=restored.state, reason=str(error))
        return Hosted(complete_hosting(self._db_path, elfie_id, _require_session_id(switching)))

    def return_to_nest(self, elfie_id: str, elfie: Elfie) -> EmbodimentSession | EmbodimentConflict:
        """Bind the resident nest body before releasing the hosted lease."""
        current = get_embodiment_session(self._db_path, elfie_id)
        if current.session_id is None:
            return EmbodimentConflict(state=current.state, reason="没有可归巢的具身会话")
        try:
            returning = start_return(self._db_path, elfie_id, current.session_id)
        except EmbodimentLeaseConflict as error:
            return EmbodimentConflict(state=current.state, reason=str(error))
        elfie.bind_body(self._nest_body_id)
        return complete_return(self._db_path, elfie_id, _require_session_id(returning))

    def heartbeat(
        self, elfie_id: str, session_id: str, *, lease_seconds: float
    ) -> EmbodimentSession:
        """Renew a hosted session's lease from a trusted device heartbeat."""
        return renew_hosting_heartbeat(
            self._db_path, elfie_id, session_id, lease_seconds=lease_seconds
        )

    def expire_stale_lease(
        self, elfie_id: str, elfie: Elfie, *, now: float | None = None
    ) -> EmbodimentSession:
        """Unbind a timed-out active body after persistence has made it offline."""
        before = get_embodiment_session(self._db_path, elfie_id)
        current = expire_stale_lease(self._db_path, elfie_id, now=now)
        if (
            current.state is EmbodimentState.OFFLINE
            and before.body_id == elfie.body_binding.current_body_id
        ):
            elfie.unbind_body()
        return current

    def recover_to_nest(self, elfie_id: str, elfie: Elfie) -> EmbodimentSession | EmbodimentConflict:
        """Reconnect the resident nest body after an acknowledged offline timeout."""
        current = get_embodiment_session(self._db_path, elfie_id)
        if current.session_id is None:
            return EmbodimentConflict(state=current.state, reason="没有可恢复的具身会话")
        if current.state is not EmbodimentState.OFFLINE:
            return EmbodimentConflict(state=current.state, reason="只有离线会话可以恢复到 Nest")
        elfie.bind_body(self._nest_body_id)
        return recover_offline_session(self._db_path, elfie_id, current.session_id)


def _require_session_id(session: EmbodimentSession) -> str:
    if session.session_id is None:
        raise RuntimeError("活动具身会话缺少 session_id")
    return session.session_id
