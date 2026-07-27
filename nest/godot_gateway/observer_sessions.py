"""Opaque Observer capability lifecycle bound to existing authenticated sessions."""

from __future__ import annotations

import secrets
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Deque, Dict

from nest.godot_gateway.observer import (
    ObserverEntityPatch,
    ObserverFrame,
    ObserverInterest,
    ObserverProjectionStore,
    ObserverSemanticEntity,
    ObserverSnapshot,
    ObserverSubscription,
    ViewerPrincipal,
    WorldChangingIntent,
)


class ObserverAuthorizationError(RuntimeError):
    """The authenticated viewer lacks the stated capability or family access."""


class ObserverBackpressureError(ObserverAuthorizationError):
    """A slow observer must discard its queue and obtain a fresh snapshot."""


@dataclass
class _CapabilitySession:
    """Server-side opaque capability binding; never retains the session token."""

    viewer: ViewerPrincipal
    session_fingerprint: str
    subscription: ObserverSubscription
    authorized_subscription: ObserverSubscription
    expires_at: float
    projections: ObserverProjectionStore
    visible_entity_ids: frozenset[str] | None = None
    delivered: ObserverFrame | None = None
    pending: Deque[ObserverFrame] = field(default_factory=deque)
    entities: Dict[str, ObserverSemanticEntity] = field(default_factory=dict)
    entity_revisions: Dict[str, int] = field(default_factory=dict)
    snapshot_required: bool = True


SemanticEntityProvider = Callable[[], Dict[str, ObserverSemanticEntity]]


class ObserverSessionRegistry:
    """Binds a server-issued capability to one authenticated web session."""

    def __init__(
        self,
        *,
        owns_elfie: Callable[[int, str], bool],
        submit_intent: Callable[[WorldChangingIntent], None],
        semantic_entities: SemanticEntityProvider | None = None,
        max_pending_frames: int = 16,
        max_intents_per_window: int = 12,
        intent_window_seconds: float = 1.0,
    ) -> None:
        if max_pending_frames < 1:
            raise ValueError("max_pending_frames must be positive")
        if max_intents_per_window < 1 or intent_window_seconds <= 0:
            raise ValueError("observer intent rate limit must be positive")
        self._owns_elfie = owns_elfie
        self._submit_intent = submit_intent
        self._semantic_entities = semantic_entities or (lambda: {})
        self._max_pending_frames = max_pending_frames
        self._max_intents_per_window = max_intents_per_window
        self._intent_window_seconds = intent_window_seconds
        self._sessions: Dict[str, _CapabilitySession] = {}
        self._intent_timestamps: Dict[str, Deque[float]] = {}

    def open_session(
        self,
        viewer: ViewerPrincipal,
        session_fingerprint: str,
        subscription: ObserverSubscription,
        *,
        expires_at: float,
    ) -> str:
        """Issue a capability after enforcing Owner/family access to Elfie scope."""
        if not self._can_access_subscription(viewer, subscription):
            raise ObserverAuthorizationError("viewer cannot observe this Elfie")
        capability = f"observer_{secrets.token_urlsafe(32)}"
        self._sessions[capability] = _CapabilitySession(
            viewer=viewer,
            session_fingerprint=session_fingerprint,
            subscription=subscription,
            authorized_subscription=subscription,
            expires_at=expires_at,
            projections=ObserverProjectionStore(generation=1),
        )
        return capability

    def update_interest(
        self,
        viewer: ViewerPrincipal,
        session_fingerprint: str,
        capability: str,
        interest: ObserverInterest,
        *,
        now: float,
    ) -> None:
        """Replace interest only after re-checking the authorized scope."""
        session = self._require_session(
            viewer, session_fingerprint, capability, now=now
        )
        if interest.subscription != session.authorized_subscription:
            raise ObserverAuthorizationError(
                "observer interest cannot change its authorized subscription"
            )
        session.subscription = interest.subscription
        session.visible_entity_ids = (
            frozenset(interest.visible_entity_ids)
            if interest.visible_entity_ids is not None
            else None
        )
        session.pending.clear()
        session.delivered = None
        session.snapshot_required = True

    def next_projection(
        self,
        viewer: ViewerPrincipal,
        session_fingerprint: str,
        capability: str,
        *,
        acknowledged_generation: int | None,
        acknowledged_sequence: int | None,
        now: float,
    ) -> ObserverFrame | None:
        """Return one bounded ordered frame, or a resync snapshot after a gap."""
        session = self._require_session(
            viewer, session_fingerprint, capability, now=now
        )
        self.publish_semantic_entities(self._semantic_entities())
        if self._acknowledgement_is_invalid(
            session,
            acknowledged_generation=acknowledged_generation,
            acknowledged_sequence=acknowledged_sequence,
        ):
            session.pending.clear()
            session.snapshot_required = True
            session.delivered = None
        if session.snapshot_required:
            snapshot = self._snapshot_for(session)
            session.snapshot_required = False
            session.delivered = snapshot
            return snapshot
        if not session.pending:
            return None
        frame = session.pending.popleft()
        session.delivered = frame
        return frame

    def publish_semantic_entities(
        self,
        entities: Dict[str, ObserverSemanticEntity],
    ) -> None:
        """Fan out filtered semantic deltas without storing geometry or physics."""
        for session in self._sessions.values():
            projected = self._filtered_entities(session, entities)
            if session.snapshot_required:
                session.entities = projected
                session.entity_revisions = dict.fromkeys(projected, 1)
                continue
            changed_ids = tuple(
                entity_id
                for entity_id in set(projected) | set(session.entities)
                if projected.get(entity_id) != session.entities.get(entity_id)
            )
            if not changed_ids:
                continue
            if len(changed_ids) != 1 or changed_ids[0] not in projected:
                session.entities = projected
                session.entity_revisions = {
                    entity_id: session.entity_revisions.get(entity_id, 0) + 1
                    for entity_id in projected
                }
                self._enqueue(session, self._snapshot_for(session))
                continue
            entity_id = changed_ids[0]
            previous = session.entities[entity_id]
            current = projected[entity_id]
            patch = _patch(previous, current)
            session.entities[entity_id] = current
            revision = session.entity_revisions.get(entity_id, 0) + 1
            session.entity_revisions[entity_id] = revision
            self._enqueue(
                session,
                session.projections.delta(
                    scope=session.subscription,
                    entity_id=entity_id,
                    entity_revision=revision,
                    patch=patch,
                ),
            )

    def submit_world_intent(
        self,
        viewer: ViewerPrincipal,
        session_fingerprint: str,
        capability: str,
        intent: WorldChangingIntent,
        *,
        now: float,
    ) -> None:
        """Authorize and deliver one typed interaction without accepting geometry."""
        self._require_session(viewer, session_fingerprint, capability, now=now)
        self._limit_intent(capability, now)
        if not self._can_change_world(viewer, intent.actor_id):
            raise ObserverAuthorizationError(
                "viewer cannot change this Elfie world state"
            )
        self._submit_intent(intent)

    def revoke_session(self, session_fingerprint: str) -> None:
        """Remove every Observer capability belonging to one logged-out session."""
        for capability, session in tuple(self._sessions.items()):
            if session.session_fingerprint == session_fingerprint:
                del self._sessions[capability]

    def _can_access_subscription(
        self,
        viewer: ViewerPrincipal,
        subscription: ObserverSubscription,
    ) -> bool:
        if subscription.kind == "room":
            return True
        if subscription.elfie_id is None:
            return False
        return self._can_change_world(viewer, subscription.elfie_id)

    def _can_change_world(self, viewer: ViewerPrincipal, elfie_id: str) -> bool:
        return viewer.role == "owner" or self._owns_elfie(viewer.user_id, elfie_id)

    def _require_session(
        self,
        viewer: ViewerPrincipal,
        session_fingerprint: str,
        capability: str,
        *,
        now: float,
    ) -> _CapabilitySession:
        session = self._sessions.get(capability)
        if (
            session is None
            or session.viewer != viewer
            or session.session_fingerprint != session_fingerprint
            or session.expires_at <= now
        ):
            if session is not None and session.expires_at <= now:
                del self._sessions[capability]
                self._intent_timestamps.pop(capability, None)
            raise ObserverAuthorizationError("invalid observer capability")
        return session

    def _acknowledgement_is_invalid(
        self,
        session: _CapabilitySession,
        *,
        acknowledged_generation: int | None,
        acknowledged_sequence: int | None,
    ) -> bool:
        delivered = session.delivered
        if delivered is None:
            return (
                acknowledged_generation is not None or acknowledged_sequence is not None
            )
        return (
            acknowledged_generation != delivered.generation
            or acknowledged_sequence != delivered.sequence
        )

    def _snapshot_for(self, session: _CapabilitySession) -> ObserverSnapshot:
        return session.projections.snapshot(
            scope=session.subscription,
            entities=session.entities,
            entity_revisions=session.entity_revisions,
        )

    def _filtered_entities(
        self,
        session: _CapabilitySession,
        entities: Dict[str, ObserverSemanticEntity],
    ) -> Dict[str, ObserverSemanticEntity]:
        visible = session.visible_entity_ids
        return {
            entity_id: entity
            for entity_id, entity in entities.items()
            if self._is_visible_to(session, entity_id, entity, visible)
        }

    def _is_visible_to(
        self,
        session: _CapabilitySession,
        entity_id: str,
        entity: ObserverSemanticEntity,
        visible: frozenset[str] | None,
    ) -> bool:
        scope = session.subscription
        in_scope = (
            entity.room_id == scope.room_id
            if scope.kind == "room"
            else entity_id == scope.elfie_id
        )
        principal_can_see = session.viewer.role == "owner" or self._owns_elfie(
            session.viewer.user_id, entity_id
        )
        return (
            in_scope and principal_can_see and (visible is None or entity_id in visible)
        )

    def _enqueue(self, session: _CapabilitySession, frame: ObserverFrame) -> None:
        if len(session.pending) >= self._max_pending_frames:
            session.pending.clear()
            session.snapshot_required = True
            return
        session.pending.append(frame)

    def _limit_intent(self, capability: str, now: float) -> None:
        timestamps = self._intent_timestamps.setdefault(capability, deque())
        cutoff = now - self._intent_window_seconds
        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()
        if len(timestamps) >= self._max_intents_per_window:
            raise ObserverBackpressureError("observer intent rate limit exceeded")
        timestamps.append(now)


def _patch(
    previous: ObserverSemanticEntity,
    current: ObserverSemanticEntity,
) -> ObserverEntityPatch:
    """Create the minimal changed semantic fields for one resident."""
    previous_fields = previous.model_dump()
    current_fields = current.model_dump()
    return ObserverEntityPatch.model_validate(
        {
            field: value
            for field, value in current_fields.items()
            if previous_fields[field] != value
        }
    )


__all__ = (
    "ObserverAuthorizationError",
    "ObserverBackpressureError",
    "ObserverSessionRegistry",
)
