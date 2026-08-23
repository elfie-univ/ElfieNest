"""Commands, queries and results for scoped Observer sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union

from pydantic import JsonValue
from typing_extensions import TypeAlias

from .port_models import ObserverEntityRecord, ObserverWorldIntent


@dataclass(frozen=True)
class ObserverPrincipal:
    user_id: int
    access: Literal["manager", "member"]


@dataclass(frozen=True)
class ObserverSubscription:
    kind: Literal["room", "elfie"]
    room_id: str | None = None
    elfie_id: str | None = None


@dataclass(frozen=True)
class OpenObserverSessionCommand:
    principal: ObserverPrincipal
    session_fingerprint: str
    subscription: ObserverSubscription


@dataclass(frozen=True)
class OpenObserverSessionResult:
    capability: str
    idle_timeout_seconds: int


@dataclass(frozen=True)
class CloseObserverSessionCommand:
    principal: ObserverPrincipal
    session_fingerprint: str
    capability: str


@dataclass(frozen=True)
class UpdateObserverInterestCommand:
    principal: ObserverPrincipal
    session_fingerprint: str
    capability: str
    subscription: ObserverSubscription
    visible_entity_ids: tuple[str, ...] | None


@dataclass(frozen=True)
class SubmitObserverIntentCommand:
    principal: ObserverPrincipal
    session_fingerprint: str
    capability: str
    intent: ObserverWorldIntent


@dataclass(frozen=True)
class NextObserverFrameQuery:
    principal: ObserverPrincipal
    session_fingerprint: str
    capability: str
    acknowledged_generation: int | None
    acknowledged_sequence: int | None


@dataclass(frozen=True)
class ObserverProjectedEntityResult:
    state: ObserverEntityRecord
    revision: int


@dataclass(frozen=True)
class ObserverEntityChangeResult:
    field: Literal[
        "room_id",
        "zone_id",
        "posture",
        "active",
        "active_command_id",
        "species_id",
        "appearance",
        "home_anchor_id",
        "mock_motion",
    ]
    value: JsonValue


@dataclass(frozen=True)
class ObserverSnapshotResult:
    generation: int
    sequence: int
    scope: ObserverSubscription
    entities: tuple[ObserverProjectedEntityResult, ...]


@dataclass(frozen=True)
class ObserverDeltaResult:
    generation: int
    sequence: int
    scope: ObserverSubscription
    entity_id: str
    entity_revision: int
    changes: tuple[ObserverEntityChangeResult, ...]


ObserverFrameResult: TypeAlias = Union[ObserverSnapshotResult, ObserverDeltaResult]
ObserverEntityField: TypeAlias = Literal[
    "room_id",
    "zone_id",
    "posture",
    "active",
    "active_command_id",
    "species_id",
    "appearance",
    "home_anchor_id",
    "mock_motion",
]


__all__ = (
    "CloseObserverSessionCommand",
    "NextObserverFrameQuery",
    "ObserverDeltaResult",
    "ObserverEntityChangeResult",
    "ObserverEntityField",
    "ObserverFrameResult",
    "ObserverPrincipal",
    "ObserverProjectedEntityResult",
    "ObserverSnapshotResult",
    "ObserverSubscription",
    "OpenObserverSessionCommand",
    "OpenObserverSessionResult",
    "SubmitObserverIntentCommand",
    "UpdateObserverInterestCommand",
)
