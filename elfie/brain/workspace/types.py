"""Typed lifecycle results and failures for the perceptual workspace."""

from __future__ import annotations

from enum import Enum, unique
from typing import NamedTuple, Optional
from uuid import uuid4

from pydantic import Field

from elfie.brain.workspace.contracts import (
    InternalPayload,
    InternalSignal,
    ProcessingFailureEvent,
    TurnFrame,
)
from elfie.message_types import (
    ActorId,
    ActorRef,
    ElfieId,
    EventId,
    FrozenContractModel,
    MessageMeta,
    Priority,
    TraceId,
    TurnId,
    UTCDateTime,
)


@unique
class WaitStatus(str, Enum):
    """Result of waiting for a workspace state change."""

    CHANGED = "changed"
    TIMED_OUT = "timed_out"
    STOPPED = "stopped"


class TriggerMetrics(FrozenContractModel):
    """O(1) trigger-policy snapshot maintained by the workspace."""

    revision: int = Field(strict=True, ge=0)
    latest_ingest_seq: int = Field(strict=True, ge=0)
    reliable_event_count: int = Field(strict=True, ge=0)
    state_key_count: int = Field(strict=True, ge=0)
    media_sample_count: int = Field(strict=True, ge=0)
    oldest_event_at: Optional[UTCDateTime]
    newest_event_at: Optional[UTCDateTime]
    oldest_social_at: Optional[UTCDateTime]
    newest_social_at: Optional[UTCDateTime]
    critical_event_count: int = Field(strict=True, ge=0)
    max_salience: float = Field(strict=True, ge=0.0, le=1.0)
    stopped: bool


class WorkspaceStorageMetrics(NamedTuple):
    """Constant-time counters exposed only to the locking workspace."""

    reliable_event_count: int
    state_key_count: int
    media_sample_count: int
    oldest_event_at: Optional[UTCDateTime]
    newest_event_at: Optional[UTCDateTime]
    oldest_social_at: Optional[UTCDateTime]
    newest_social_at: Optional[UTCDateTime]
    critical_event_count: int
    max_salience: float


class WorkspaceClaim(NamedTuple):
    """One active frame-to-turn ownership record."""

    frame: TurnFrame
    turn_id: TurnId


class ActiveClaimError(RuntimeError):
    """Raised when a second frame claim is attempted."""

    __slots__ = ("frame_id",)

    def __init__(self, frame_id: EventId) -> None:
        self.frame_id = frame_id
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"frame {self.frame_id} is already active"


class FrameLifecycleError(RuntimeError):
    """Raised when a frame or turn ID does not match workspace state."""

    __slots__ = ("reason",)

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)

    def __str__(self) -> str:
        return self.reason


def build_processing_failure(
    *,
    elfie_id: ElfieId,
    failed_frame_id: EventId,
    failed_cutoff_seq: int,
    reason: str,
    occurred_at: UTCDateTime,
) -> ProcessingFailureEvent:
    """Create non-recursive reliable evidence for terminal frame failure."""
    return ProcessingFailureEvent(
        meta=MessageMeta(
            event_id=EventId(f"processing_failure_{uuid4().hex}"),
            elfie_id=elfie_id,
            source=ActorRef(
                actor_id=ActorId("perceptual-workspace"),
                source_kind="internal",
            ),
            occurred_at=occurred_at,
            received_at=occurred_at,
            trace_id=TraceId(f"trace_{uuid4().hex}"),
            causation_id=failed_frame_id,
            priority=Priority.HIGH,
        ),
        payload=InternalPayload(
            type="internal",
            signal=InternalSignal.PROCESSING_FAILURE,
            detail=reason,
        ),
        salience=1.0,
        failed_frame_id=failed_frame_id,
        failed_cutoff_seq=failed_cutoff_seq,
        failure_count=3,
        failure_reason=reason,
    )


__all__ = (
    "ActiveClaimError",
    "FrameLifecycleError",
    "ProcessingFailureEvent",
    "TriggerMetrics",
    "WaitStatus",
    "WorkspaceStorageMetrics",
    "WorkspaceClaim",
    "build_processing_failure",
)
