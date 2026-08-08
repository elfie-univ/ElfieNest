"""Versioned, capability-scoped Observer protocol models and session state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator
from typing_extensions import TypeAlias

ObserverEntity: TypeAlias = Dict[str, JsonValue]


class _ProtocolModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AuthorityHello(_ProtocolModel):
    """Internal one-time credential for the sole world authority."""

    protocol: Literal[3]
    role: Literal["authority"]
    runtime_id: str = Field(min_length=1)
    nonce: str = Field(min_length=1)


class ObserverSubscription(_ProtocolModel):
    """A semantic projection scope, intentionally without camera state."""

    kind: Literal["room", "elfie"]
    room_id: Optional[str] = Field(default=None, min_length=1)
    elfie_id: Optional[str] = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _validate_scope(self) -> ObserverSubscription:
        if self.kind == "room":
            if self.room_id is None or self.elfie_id is not None:
                raise ValueError("room subscription requires only room_id")
        elif self.elfie_id is None or self.room_id is not None:
            raise ValueError("elfie subscription requires only elfie_id")
        return self


class ObserverHello(_ProtocolModel):
    """Untrusted observer request; login supplies its viewer capability separately."""

    protocol: Literal[3]
    role: Literal["observer"]
    subscription: ObserverSubscription


class ObserverInterest(_ProtocolModel):
    """A viewer-selected subset of an already-authorized Observer scope.

    ``None`` retains every entity in the subscription.  A non-empty tuple can
    only reduce that result; it cannot widen room or Elfie authorization.
    """

    subscription: ObserverSubscription
    visible_entity_ids: Optional[tuple[str, ...]] = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _validate_visible_entity_ids(self) -> ObserverInterest:
        ids = self.visible_entity_ids
        if ids is not None and (not ids or len(ids) != len(set(ids))):
            raise ValueError("visible entity interest must be non-empty and unique")
        return self


class ObserverIntent(str, Enum):
    """Closed local Observer navigation intents with no world-write meaning."""

    REQUEST_RESYNC = "request_resync"
    FOCUS_ROOM = "focus_room"
    FOCUS_ELFIE = "focus_elfie"


@dataclass(frozen=True)
class ObserverScope:
    """Read scope issued after authenticated family access is checked."""

    family_id: str
    room_id: str | None
    elfie_id: str | None


@dataclass(frozen=True)
class ObserverDescriptor:
    """Capability metadata without authority credentials or transform rights."""

    session_id: str
    scope: ObserverScope
    generation: int
    sequence: int
    allowed_intents: frozenset[ObserverIntent]


class WorldChangingIntent(_ProtocolModel):
    """A bounded world-changing request with no transform representation."""

    kind: Literal["request_interaction"]
    actor_id: str = Field(min_length=1)
    interaction: Literal["greet", "rest"]


class ObserverSemanticEntity(_ProtocolModel):
    """The complete geometry-free semantic state that Python may project."""

    room_id: str = Field(default="local-nest", min_length=1)
    zone_id: Optional[str] = Field(default=None, min_length=1)
    posture: str = Field(default="standing", min_length=1)
    active: bool = True
    active_command_id: Optional[str] = Field(default=None, min_length=1)
    species_id: Optional[str] = Field(default=None, min_length=1)
    appearance: Dict[str, JsonValue] = Field(default_factory=dict)
    home_anchor_id: Optional[str] = Field(default=None, min_length=1)


class ObserverEntityPatch(_ProtocolModel):
    """A non-empty partial update to one geometry-free semantic entity."""

    room_id: Optional[str] = Field(default=None, min_length=1)
    zone_id: Optional[str] = Field(default=None, min_length=1)
    posture: Optional[str] = Field(default=None, min_length=1)
    active: Optional[bool] = None
    active_command_id: Optional[str] = Field(default=None, min_length=1)
    species_id: Optional[str] = Field(default=None, min_length=1)
    appearance: Optional[Dict[str, JsonValue]] = None
    home_anchor_id: Optional[str] = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _require_changed_field(self) -> ObserverEntityPatch:
        if not self.model_fields_set:
            raise ValueError("observer entity patch must not be empty")
        return self


class ObserverSnapshot(_ProtocolModel):
    """Complete semantic state for one observer subscription."""

    protocol: Literal[3] = 3
    kind: Literal["snapshot"] = "snapshot"
    generation: int = Field(ge=1)
    sequence: int = Field(ge=1)
    scope: ObserverSubscription
    entities: Dict[str, ObserverSemanticEntity]
    entity_revisions: Dict[str, int]

    @model_validator(mode="after")
    def _validate_entity_revisions(self) -> ObserverSnapshot:
        if set(self.entities) != set(self.entity_revisions):
            raise ValueError("snapshot entity revisions must match entities")
        if any(revision < 1 for revision in self.entity_revisions.values()):
            raise ValueError("snapshot entity revisions must be positive")
        return self


class ObserverDelta(_ProtocolModel):
    """One ordered semantic entity change for a single subscription."""

    protocol: Literal[3] = 3
    kind: Literal["delta"] = "delta"
    generation: int = Field(ge=1)
    sequence: int = Field(ge=1)
    scope: ObserverSubscription
    entity_id: str = Field(min_length=1)
    entity_revision: int = Field(ge=1)
    patch: ObserverEntityPatch


ObserverFrame: TypeAlias = Union[ObserverSnapshot, ObserverDelta]


@dataclass(frozen=True)
class ViewerPrincipal:
    """Authenticated product principal projected from the existing web session."""

    user_id: int
    role: Literal["owner", "user"]


@dataclass(frozen=True)
class ObserverConsumeResult:
    """Observable result of processing exactly one projection frame."""

    resync_required: bool


class ObserverConsumer:
    """Local observer view that refuses gaps and generation changes."""

    def __init__(self) -> None:
        self._generation: int | None = None
        self._sequence = 0
        self._entities: Dict[str, ObserverSemanticEntity] = {}
        self._entity_revisions: Dict[str, int] = {}

    @property
    def entities(self) -> Dict[str, ObserverEntity]:
        return {
            entity_id: entity.model_dump(mode="json")
            for entity_id, entity in self._entities.items()
        }

    def accept(self, frame: ObserverFrame) -> ObserverConsumeResult:
        """Apply only the next matching frame; otherwise require a fresh snapshot."""
        if not isinstance(frame, ObserverSnapshot) and self._generation is None:
            return ObserverConsumeResult(resync_required=True)
        if self._generation is not None and frame.generation != self._generation:
            return ObserverConsumeResult(resync_required=True)
        if frame.sequence != self._sequence + 1:
            return ObserverConsumeResult(resync_required=True)
        if isinstance(frame, ObserverSnapshot):
            self._generation = frame.generation
            self._sequence = frame.sequence
            self._entities = dict(frame.entities)
            self._entity_revisions = dict(frame.entity_revisions)
        else:
            current_revision = self._entity_revisions.get(frame.entity_id, 0)
            if frame.entity_revision <= current_revision:
                return ObserverConsumeResult(resync_required=True)
            current = self._entities.get(frame.entity_id)
            if current is None:
                return ObserverConsumeResult(resync_required=True)
            self._entities[frame.entity_id] = current.model_copy(
                update=frame.patch.model_dump(exclude_unset=True)
            )
            self._entity_revisions[frame.entity_id] = frame.entity_revision
            self._sequence = frame.sequence
        return ObserverConsumeResult(resync_required=False)


class ObserverProjectionStore:
    """Produces semantic snapshot/delta frames for one authority generation."""

    def __init__(self, *, generation: int) -> None:
        self._generation = generation
        self._sequence = 0

    def snapshot(
        self,
        *,
        scope: ObserverSubscription,
        entities: Dict[str, ObserverSemanticEntity],
        entity_revisions: Dict[str, int],
    ) -> ObserverSnapshot:
        """Issue the next complete projection frame."""
        self._sequence += 1
        return ObserverSnapshot(
            generation=self._generation,
            sequence=self._sequence,
            scope=scope,
            entities=entities,
            entity_revisions=entity_revisions,
        )

    def delta(
        self,
        *,
        scope: ObserverSubscription,
        entity_id: str,
        entity_revision: int,
        patch: ObserverEntityPatch,
        generation: int | None = None,
        sequence: int | None = None,
    ) -> ObserverDelta:
        """Issue one semantic patch; overrides exist only for replay fixtures."""
        self._sequence += 1
        return ObserverDelta(
            generation=self._generation if generation is None else generation,
            sequence=self._sequence if sequence is None else sequence,
            scope=scope,
            entity_id=entity_id,
            entity_revision=entity_revision,
            patch=patch,
        )

    def new_consumer(self) -> ObserverConsumer:
        """Construct a blank local projection consumer for one viewer session."""
        return ObserverConsumer()


def parse_authority_hello(raw: Dict[str, JsonValue]) -> AuthorityHello:
    """Parse the internal authority handshake, including its nonce only here."""
    return AuthorityHello.model_validate(raw)


def parse_observer_hello(raw: Dict[str, JsonValue]) -> ObserverHello:
    """Parse a public observer hello without accepting authority credentials."""
    return ObserverHello.model_validate(raw)


__all__ = (
    "AuthorityHello",
    "ObserverConsumeResult",
    "ObserverConsumer",
    "ObserverDelta",
    "ObserverDescriptor",
    "ObserverEntityPatch",
    "ObserverFrame",
    "ObserverHello",
    "ObserverInterest",
    "ObserverIntent",
    "ObserverProjectionStore",
    "ObserverSnapshot",
    "ObserverScope",
    "ObserverSemanticEntity",
    "ObserverSubscription",
    "ViewerPrincipal",
    "WorldChangingIntent",
    "parse_authority_hello",
    "parse_observer_hello",
)
