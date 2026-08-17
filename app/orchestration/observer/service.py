"""Capability-scoped Observer workflow over existing Elfie and world facts."""

from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass, field
from typing import Deque

from pydantic import JsonValue

from app.features.accounts import AccountPrincipal, AccountsService
from app.features.elfies import ElfiesError, ElfiesService, ListVisibleElfiesQuery

from .errors import ObserverForbidden, ObserverRateLimited, ObserverUnavailable
from .models import (
    NextObserverFrameQuery,
    ObserverDeltaResult,
    ObserverEntityChangeResult,
    ObserverEntityField,
    ObserverFrameResult,
    ObserverPrincipal,
    ObserverProjectedEntityResult,
    ObserverSnapshotResult,
    ObserverSubscription,
    OpenObserverSessionCommand,
    OpenObserverSessionResult,
    SubmitObserverIntentCommand,
    UpdateObserverInterestCommand,
)
from .port_models import ObserverEntityRecord
from .ports import (
    ObserverCapabilityIssuerPort,
    ObserverClockPort,
    ObserverPortError,
    ObserverWorldPort,
)


@dataclass
class _ObserverSession:
    principal: ObserverPrincipal
    session_fingerprint: str
    subscription: ObserverSubscription
    authorized_subscription: ObserverSubscription
    expires_at: float
    generation: int = 1
    sequence: int = 0
    visible_entity_ids: frozenset[str] | None = None
    delivered: ObserverFrameResult | None = None
    pending: Deque[ObserverFrameResult] = field(default_factory=deque)
    entities: dict[str, ObserverEntityRecord] = field(default_factory=dict)
    entity_revisions: dict[str, int] = field(default_factory=dict)
    snapshot_required: bool = True


class ObserverFacade:
    """Own Observer principals, capabilities, projections and allowed intents."""

    def __init__(
        self,
        *,
        accounts: AccountsService,
        elfies: ElfiesService,
        world: ObserverWorldPort,
        clock: ObserverClockPort,
        capabilities: ObserverCapabilityIssuerPort,
        max_pending_frames: int = 16,
        max_intents_per_window: int = 12,
        intent_window_seconds: float = 1.0,
    ) -> None:
        if max_pending_frames < 1:
            raise ValueError("max_pending_frames must be positive")
        if max_intents_per_window < 1 or intent_window_seconds <= 0:
            raise ValueError("observer intent rate limit must be positive")
        self._accounts = accounts
        self._elfies = elfies
        self._world = world
        self._clock = clock
        self._capabilities = capabilities
        self._max_pending_frames = max_pending_frames
        self._max_intents_per_window = max_intents_per_window
        self._intent_window_seconds = intent_window_seconds
        self._sessions: dict[str, _ObserverSession] = {}
        self._intent_timestamps: dict[str, Deque[float]] = {}

    def open_session(
        self,
        command: OpenObserverSessionCommand,
    ) -> OpenObserverSessionResult:
        if not self._can_access_subscription(command.principal, command.subscription):
            raise ObserverForbidden("viewer cannot observe this Elfie")
        capability = self._capabilities.issue()
        now = self._clock.now()
        session_ttl_seconds = self._accounts.session_ttl_seconds()
        if session_ttl_seconds <= 0:
            raise ObserverUnavailable("Observer session policy unavailable")
        self._sessions[capability] = _ObserverSession(
            principal=command.principal,
            session_fingerprint=command.session_fingerprint,
            subscription=command.subscription,
            authorized_subscription=command.subscription,
            expires_at=now + session_ttl_seconds,
        )
        return OpenObserverSessionResult(capability=capability)

    def update_interest(self, command: UpdateObserverInterestCommand) -> None:
        session = self._require_session(
            command.principal,
            command.session_fingerprint,
            command.capability,
        )
        if command.subscription != session.authorized_subscription:
            raise ObserverForbidden(
                "observer interest cannot change its authorized subscription"
            )
        session.subscription = command.subscription
        session.visible_entity_ids = (
            None
            if command.visible_entity_ids is None
            else frozenset(command.visible_entity_ids)
        )
        session.pending.clear()
        session.delivered = None
        session.snapshot_required = True

    def next_frame(
        self,
        query: NextObserverFrameQuery,
    ) -> ObserverFrameResult | None:
        session = self._require_session(
            query.principal,
            query.session_fingerprint,
            query.capability,
        )
        self._publish(self._entities())
        if self._acknowledgement_is_invalid(
            session,
            acknowledged_generation=query.acknowledged_generation,
            acknowledged_sequence=query.acknowledged_sequence,
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

    def submit_intent(self, command: SubmitObserverIntentCommand) -> None:
        self._require_session(
            command.principal,
            command.session_fingerprint,
            command.capability,
        )
        self._limit_intent(command.capability)
        if not self._can_change_world(command.principal, command.intent.actor_id):
            raise ObserverForbidden("viewer cannot change this Elfie world state")
        try:
            self._world.submit_intent(command.intent)
        except ObserverPortError as error:
            raise ObserverUnavailable(
                "observer world intent sink unavailable"
            ) from error

    def revoke_session(self, session_fingerprint: str) -> None:
        for capability, session in tuple(self._sessions.items()):
            if session.session_fingerprint == session_fingerprint:
                del self._sessions[capability]
                self._intent_timestamps.pop(capability, None)

    def _entities(self) -> tuple[ObserverEntityRecord, ...]:
        try:
            return self._world.list_entities()
        except ObserverPortError as error:
            raise ObserverUnavailable("observer projection unavailable") from error

    def _publish(self, entities: tuple[ObserverEntityRecord, ...]) -> None:
        by_id = {entity.entity_id: entity for entity in entities}
        for session in self._sessions.values():
            projected = self._filtered_entities(session, by_id)
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
            session.entities[entity_id] = current
            revision = session.entity_revisions.get(entity_id, 0) + 1
            session.entity_revisions[entity_id] = revision
            session.sequence += 1
            self._enqueue(
                session,
                ObserverDeltaResult(
                    generation=session.generation,
                    sequence=session.sequence,
                    scope=session.subscription,
                    entity_id=entity_id,
                    entity_revision=revision,
                    changes=_changes(previous, current),
                ),
            )

    def _can_access_subscription(
        self,
        principal: ObserverPrincipal,
        subscription: ObserverSubscription,
    ) -> bool:
        if subscription.kind == "room":
            return True
        return subscription.elfie_id is not None and self._can_change_world(
            principal, subscription.elfie_id
        )

    def _can_change_world(
        self,
        principal: ObserverPrincipal,
        elfie_id: str,
    ) -> bool:
        if principal.access == "manager":
            return True
        try:
            visible = self._elfies.list_visible(
                _account_principal(principal),
                ListVisibleElfiesQuery(),
            )
        except ElfiesError as error:
            raise ObserverUnavailable("Elfie authorization unavailable") from error
        return any(item.profile.elfie_id == elfie_id for item in visible)

    def _require_session(
        self,
        principal: ObserverPrincipal,
        session_fingerprint: str,
        capability: str,
    ) -> _ObserverSession:
        session = self._sessions.get(capability)
        now = self._clock.now()
        if (
            session is None
            or session.principal != principal
            or session.session_fingerprint != session_fingerprint
            or session.expires_at <= now
        ):
            if session is not None and session.expires_at <= now:
                del self._sessions[capability]
                self._intent_timestamps.pop(capability, None)
            raise ObserverForbidden("invalid observer capability")
        return session

    @staticmethod
    def _acknowledgement_is_invalid(
        session: _ObserverSession,
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

    @staticmethod
    def _snapshot_for(session: _ObserverSession) -> ObserverSnapshotResult:
        session.sequence += 1
        return ObserverSnapshotResult(
            generation=session.generation,
            sequence=session.sequence,
            scope=session.subscription,
            entities=tuple(
                ObserverProjectedEntityResult(
                    state=entity,
                    revision=session.entity_revisions[entity_id],
                )
                for entity_id, entity in sorted(session.entities.items())
            ),
        )

    def _filtered_entities(
        self,
        session: _ObserverSession,
        entities: dict[str, ObserverEntityRecord],
    ) -> dict[str, ObserverEntityRecord]:
        return {
            entity_id: entity
            for entity_id, entity in entities.items()
            if self._is_visible_to(session, entity_id, entity)
        }

    def _is_visible_to(
        self,
        session: _ObserverSession,
        entity_id: str,
        entity: ObserverEntityRecord,
    ) -> bool:
        scope = session.subscription
        in_scope = (
            entity.room_id == scope.room_id
            if scope.kind == "room"
            else entity_id == scope.elfie_id
        )
        visible = session.visible_entity_ids
        return (
            in_scope
            and self._can_change_world(session.principal, entity_id)
            and (visible is None or entity_id in visible)
        )

    def _enqueue(
        self,
        session: _ObserverSession,
        frame: ObserverFrameResult,
    ) -> None:
        if len(session.pending) >= self._max_pending_frames:
            session.pending.clear()
            session.snapshot_required = True
            return
        session.pending.append(frame)

    def _limit_intent(self, capability: str) -> None:
        now = self._clock.now()
        timestamps = self._intent_timestamps.setdefault(capability, deque())
        cutoff = now - self._intent_window_seconds
        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()
        if len(timestamps) >= self._max_intents_per_window:
            raise ObserverRateLimited("observer intent rate limit exceeded")
        timestamps.append(now)


def session_token_fingerprint(token: str) -> str:
    """Bind capabilities to a login without retaining its raw session token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _account_principal(principal: ObserverPrincipal) -> AccountPrincipal:
    return AccountPrincipal(
        principal.user_id,
        "observer",
        "owner" if principal.access == "manager" else "user",
        "manage" if principal.access == "manager" else "chat",
    )


def _changes(
    previous: ObserverEntityRecord,
    current: ObserverEntityRecord,
) -> tuple[ObserverEntityChangeResult, ...]:
    previous_fields = _entity_fields(previous)
    current_fields = _entity_fields(current)
    fields: tuple[ObserverEntityField, ...] = (
        "room_id",
        "zone_id",
        "posture",
        "active",
        "active_command_id",
        "species_id",
        "appearance",
        "home_anchor_id",
        "mock_motion",
    )
    return tuple(
        ObserverEntityChangeResult(field=field, value=current_fields[field])
        for field in fields
        if previous_fields[field] != current_fields[field]
    )


def _entity_fields(
    entity: ObserverEntityRecord,
) -> dict[ObserverEntityField, JsonValue]:
    return {
        "room_id": entity.room_id,
        "zone_id": entity.zone_id,
        "posture": entity.posture,
        "active": entity.active,
        "active_command_id": entity.active_command_id,
        "species_id": entity.species_id,
        "appearance": dict(entity.appearance),
        "home_anchor_id": entity.home_anchor_id,
        "mock_motion": (
            entity.mock_motion.model_dump(mode="json")
            if entity.mock_motion is not None
            else None
        ),
    }


__all__ = ("ObserverFacade", "session_token_fingerprint")
