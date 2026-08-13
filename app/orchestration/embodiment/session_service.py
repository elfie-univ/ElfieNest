"""Coordinate the real Elfie body binding with durable lease transitions."""

from __future__ import annotations

from app.features.accounts import AccountPrincipal, is_manager
from elfie.public import BodyPort, Elfie

from .errors import EmbodimentForbidden, EmbodimentUnavailable
from .models import (
    EmbodimentConflict,
    EmbodimentSession,
    Hosted,
    HostingFailed,
    HostingResult,
    ListEmbodimentSessionsQuery,
)
from .ports import (
    EmbodimentLeaseConflict,
    EmbodimentLeasePort,
    EmbodimentLeasePortError,
)
from .state_machine import EmbodimentState


class EmbodimentSessionService:
    """Keep durable lease state and an Elfie's sole active BodyPort aligned."""

    def __init__(self, leases: EmbodimentLeasePort) -> None:
        self._leases = leases

    def get_session(self, elfie_id: str) -> EmbodimentSession:
        return self._leases.get(elfie_id)

    def list_sessions(
        self,
        principal: AccountPrincipal,
        query: ListEmbodimentSessionsQuery,
    ) -> tuple[EmbodimentSession, ...]:
        """Return the existing durable session projection to managers only."""
        del query
        if not is_manager(principal.role):
            raise EmbodimentForbidden("Embodiment sessions require a manager")
        try:
            return self._leases.list_sessions()
        except EmbodimentLeasePortError as error:
            raise EmbodimentUnavailable("Embodiment sessions unavailable") from error

    def host(
        self, elfie_id: str, elfie: Elfie, body: BodyPort, *, lease_seconds: float
    ) -> HostingResult:
        """Acquire first, then bind; release the durable lease if binding fails."""
        try:
            switching = self._leases.begin_hosting(
                elfie_id, body.body_id, lease_seconds=lease_seconds
            )
        except EmbodimentLeaseConflict as error:
            current = self._leases.get(elfie_id)
            return EmbodimentConflict(state=current.state, reason=str(error))

        if not elfie.has_body(body.body_id):
            elfie.register_body(body)
        elif not elfie.is_registered_body(body):
            restored = self._leases.abort_hosting(elfie_id, switching.lease_version)
            return HostingFailed(
                restored_state=restored.state,
                reason="body_id 已注册为另一个身体实例",
            )
        try:
            elfie.bind_body(body.body_id)
        except RuntimeError as error:
            restored = self._leases.abort_hosting(elfie_id, switching.lease_version)
            return HostingFailed(restored_state=restored.state, reason=str(error))
        return Hosted(self._leases.complete_hosting(elfie_id, switching.lease_version))

    def return_to_nest(
        self, elfie_id: str, elfie: Elfie, *, nest_body_id: str
    ) -> EmbodimentSession | EmbodimentConflict:
        """Bind the resident nest body before releasing the hosted lease."""
        current = self._leases.get(elfie_id)
        if current.lease_version == 0:
            return EmbodimentConflict(
                state=current.state, reason="没有可归巢的具身会话"
            )
        try:
            returning = self._leases.start_return(elfie_id, current.lease_version)
        except EmbodimentLeaseConflict as error:
            return EmbodimentConflict(state=current.state, reason=str(error))
        elfie.bind_body(nest_body_id)
        return self._leases.complete_return(elfie_id, returning.lease_version)

    def heartbeat(
        self, elfie_id: str, lease_version: int, *, lease_seconds: float
    ) -> EmbodimentSession:
        """Renew a hosted session's lease from a trusted body heartbeat."""
        return self._leases.heartbeat(
            elfie_id, lease_version, lease_seconds=lease_seconds
        )

    def expire_stale_lease(
        self, elfie_id: str, elfie: Elfie, *, now: float | None = None
    ) -> EmbodimentSession:
        """Unbind a timed-out active body after persistence has made it offline."""
        before = self._leases.get(elfie_id)
        current = self._leases.expire(elfie_id, now=now)
        if (
            current.state is EmbodimentState.OFFLINE
            and before.body_id == elfie.current_body_id
        ):
            elfie.unbind_body()
        return current

    def recover_to_nest(
        self, elfie_id: str, elfie: Elfie, *, nest_body_id: str
    ) -> EmbodimentSession | EmbodimentConflict:
        """Reconnect the resident nest body after an acknowledged offline timeout."""
        current = self._leases.get(elfie_id)
        if current.lease_version == 0:
            return EmbodimentConflict(
                state=current.state, reason="没有可恢复的具身会话"
            )
        if current.state is not EmbodimentState.OFFLINE:
            return EmbodimentConflict(
                state=current.state, reason="只有离线会话可以恢复到 Nest"
            )
        elfie.bind_body(nest_body_id)
        return self._leases.recover(elfie_id, current.lease_version)


__all__ = ("EmbodimentSessionService",)
