"""Typed observation surface shared by every brain boundary.

Every observable brain boundary emits one immutable ``BrainObservation``
envelope through a single ``BrainObservationSink``. Each boundary owns a
named frozen payload model carried under ``payload``, replacing the former
ad-hoc dict callbacks. Observation is strictly side-effect free for the
brain: emit sites guard on ``sink is not None`` before constructing an
envelope, so an unwired production path pays zero allocation cost, and a
sink must never let collection failures escape into brain behavior.

This module stays domain-pure: it imports only ``elfie.message_types``
primitives and never ``infrastructure``, ``app`` or ``devtools``.
"""

from __future__ import annotations

from enum import Enum, unique
from typing import Generic, Optional, Protocol, Tuple, TypeVar, runtime_checkable

from pydantic import Field

from elfie.message_types import FrozenContractModel, UTCDateTime

__all__ = (
    "BrainObservation",
    "BrainObservationSink",
    "NoOpSink",
    "ObservationError",
    "ObservationStatus",
)

TPayload = TypeVar("TPayload")


@unique
class ObservationStatus(str, Enum):
    """Lifecycle state of one observation record."""

    completed = "completed"
    failed = "failed"
    skipped = "skipped"
    degraded = "degraded"


class ObservationError(FrozenContractModel):
    """Failure details carried by failed observations.

    ``message`` must already be sanitized by the emit site; the envelope
    only transports it.
    """

    type: str
    message: str


class BrainObservation(FrozenContractModel, Generic[TPayload]):
    """Immutable envelope shared by every brain-boundary observation.

    ``payload`` holds the boundary-owned named payload model, so callers
    use ``BrainObservation[MemoryTurnOpened](...)`` to pin the payload
    type. Causal chaining fields (``turn_id``, ``frame_id``,
    ``cause_event_ids``) link records without building dependency edges.
    """

    schema_version: int = 1
    boundary: str
    kind: str
    sequence: int
    # Lax per-field override: emit sites may pass an ISO-8601 UTC string
    # for ergonomic construction; it is normalized to an aware UTC
    # datetime, and non-UTC input is still rejected by UTCDateTime.
    captured_at: UTCDateTime = Field(strict=False)
    turn_id: str
    frame_id: str
    cause_event_ids: Tuple[str, ...] = ()
    duration_ms: Optional[float] = None
    status: ObservationStatus
    error: Optional[ObservationError] = None
    payload: TPayload


@runtime_checkable
class BrainObservationSink(Protocol):
    """Consumer contract for brain observations.

    Implementations MUST be thread-safe: ``emit`` and ``snapshot`` are
    called concurrently from the cognitive worker thread and the
    coordinator thread, so shared state requires internal locking.

    ``emit`` MUST NOT raise: observation collection must never affect
    brain behavior. Implementations absorb or log their own failures
    instead of propagating them to the emit site.
    """

    def emit(self, event: BrainObservation) -> None:
        """Record one observation; never raises."""

    def snapshot(self) -> Tuple[BrainObservation, ...]:
        """Return the observations recorded so far, in emit order."""


class NoOpSink:
    """Stateless null sink: discards every event and never raises.

    Having no mutable state makes it trivially thread-safe for
    concurrent use from any thread.
    """

    def emit(self, event: BrainObservation) -> None:
        """Discard the observation without recording it."""

    def snapshot(self) -> Tuple[BrainObservation, ...]:
        """Always return an empty snapshot."""
        return ()
