"""Strict perception contracts at the Brain root boundary."""

from __future__ import annotations

from enum import Enum, unique
from typing import Annotated, Literal, Optional, Tuple, Union

from pydantic import Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError
from typing_extensions import TypeAlias

from elfie.message_types import (
    ActorRef,
    ElfieId,
    ErrorInfo,
    EventId,
    FrozenContractModel,
    IntentId,
    MediaRef,
    MessageMeta,
    PlanId,
    TurnId,
    UTCDateTime,
)

_NonBlankText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, pattern=r".*\S.*"),
]
_Revision = Annotated[int, Field(strict=True, ge=0)]
_Sequence = Annotated[int, Field(strict=True, ge=0)]
_Count = Annotated[int, Field(strict=True, ge=1)]
_Salience = Annotated[float, Field(strict=True, ge=0.0, le=1.0)]
_StateScalar: TypeAlias = Union[bool, int, float, str]


@unique
class PhysicalModality(str, Enum):
    """Normalized physical modalities accepted from NervousSystem adapters."""

    UTTERANCE = "utterance"
    VISION = "vision"
    TOUCH = "touch"
    PROPRIOCEPTION = "proprioception"
    ENVIRONMENT = "environment"
    CONNECTION = "connection"


@unique
class ExecutionStatus(str, Enum):
    """Normalized lifecycle states emitted by output executors."""

    ACCEPTED = "accepted"
    STARTED = "started"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


@unique
class InternalSignal(str, Enum):
    """Coordinator-owned signals that may enter the perceptual workspace."""

    CLOCK = "clock"
    AUTONOMOUS_DEADLINE = "autonomous_deadline"
    MEMORY = "memory"
    EMOTION = "emotion"
    HOMEOSTASIS = "homeostasis"
    PROCESSING_FAILURE = "processing_failure"


@unique
class TriggerReason(str, Enum):
    """Reasons the coordinator may seal a perception frame."""

    EMERGENCY = "emergency"
    CONVERSATION_QUIET = "conversation_quiet"
    CONVERSATION_HARD_MAX = "conversation_hard_max"
    SALIENCE = "salience"
    CAPACITY = "capacity"
    OLDEST_EVENT = "oldest_event"
    AUTONOMOUS = "autonomous"
    MANUAL = "manual"


@unique
class IngestDisposition(str, Enum):
    """Observable result of publishing one perception write."""

    ACCEPTED = "accepted"
    COALESCED = "coalesced"
    DUPLICATE = "duplicate"
    BACKPRESSURED = "backpressured"
    REJECTED = "rejected"


class PhysicalPayload(FrozenContractModel):
    """A normalized physical observation from the current Body path."""

    type: Literal["physical"]
    body_id: _NonBlankText
    modality: PhysicalModality
    content: _NonBlankText
    media: Tuple[MediaRef, ...] = ()


class SocialPayload(FrozenContractModel):
    """A social message normalized by a Communication adapter."""

    type: Literal["social"]
    channel_id: _NonBlankText
    conversation_id: _NonBlankText
    sender: ActorRef
    content: _NonBlankText
    reply_to_event_id: Optional[EventId] = None
    media: Tuple[MediaRef, ...] = ()


class ExecutionPayload(FrozenContractModel):
    """A normalized receipt returned by a typed output executor."""

    type: Literal["execution"]
    receipt_id: EventId
    plan_id: PlanId
    turn_id: TurnId
    intent_id: IntentId
    executor: Literal["body", "communication", "internal"]
    status: ExecutionStatus
    error: Optional[ErrorInfo] = None


class InternalPayload(FrozenContractModel):
    """A coordinator-owned internal signal represented as inert data."""

    type: Literal["internal"]
    signal: InternalSignal
    detail: _NonBlankText


PerceptionPayload: TypeAlias = Annotated[
    Union[PhysicalPayload, SocialPayload, ExecutionPayload, InternalPayload],
    Field(discriminator="type"),
]


class PerceptionEvent(FrozenContractModel):
    """A reliable, ordered event candidate for the workspace journal."""

    meta: MessageMeta
    payload: PerceptionPayload
    salience: _Salience = 0.5


class ProcessingFailureEvent(PerceptionEvent):
    """Reliable evidence emitted after a frame fails three times."""

    failed_frame_id: EventId
    failed_cutoff_seq: _Sequence
    failure_count: _Count
    failure_reason: _NonBlankText


PerceptionJournalEvent: TypeAlias = Union[
    ProcessingFailureEvent,
    PerceptionEvent,
]


class PerceptionStateUpdate(FrozenContractModel):
    """A latest-only state-board update with an explicit source revision."""

    meta: MessageMeta
    state_key: _NonBlankText
    revision: _Revision
    value: _StateScalar


class PerceptionMediaSample(FrozenContractModel):
    """A bounded media-stream sample that references external storage."""

    meta: MessageMeta
    stream_id: _NonBlankText
    ordinal: _Sequence
    captured_at: UTCDateTime
    media: MediaRef


PerceptionWrite: TypeAlias = Union[
    PerceptionEvent,
    PerceptionStateUpdate,
    PerceptionMediaSample,
]


class CoalescedSummary(FrozenContractModel):
    """Observable evidence that repeated state updates were coalesced."""

    key: _NonBlankText
    count: _Count
    latest_event_id: Optional[EventId]


class DroppedSummary(FrozenContractModel):
    """Observable evidence for intentionally dropped bounded samples."""

    reason: _NonBlankText
    count: _Count
    event_ids: Tuple[EventId, ...]


class IngestReceipt(FrozenContractModel):
    """Backpressure-aware result returned to a perception producer."""

    event_id: EventId
    disposition: IngestDisposition
    ingest_seq: Optional[_Sequence]
    retryable: bool
    reason: Optional[_NonBlankText]

    @model_validator(mode="after")
    def validate_sequence(self) -> IngestReceipt:
        """Require sequence numbers only for writes retained by the workspace."""
        retained = self.disposition in {
            IngestDisposition.ACCEPTED,
            IngestDisposition.COALESCED,
            IngestDisposition.DUPLICATE,
        }
        if retained != (self.ingest_seq is not None):
            raise PydanticCustomError(
                "ingest_sequence",
                "ingest_seq must be present exactly when a write is retained",
            )
        return self


class PerceptionFrame(FrozenContractModel):
    """An immutable cutoff of ordered journal, state, and media inputs."""

    schema_version: Literal[1] = 1
    frame_id: EventId
    elfie_id: ElfieId
    revision: _Revision
    captured_at: UTCDateTime
    cutoff_seq: _Sequence
    trigger_reason: TriggerReason
    events: Tuple[PerceptionJournalEvent, ...] = ()
    state_updates: Tuple[PerceptionStateUpdate, ...] = ()
    media_samples: Tuple[PerceptionMediaSample, ...] = ()
    coalesced: Tuple[CoalescedSummary, ...] = ()
    dropped: Tuple[DroppedSummary, ...] = ()

    @model_validator(mode="after")
    def validate_identity(self) -> PerceptionFrame:
        """Keep one Elfie identity and unique event IDs within a sealed frame."""
        writes = self.events + self.state_updates + self.media_samples
        foreign_ids = tuple(
            write.meta.event_id
            for write in writes
            if write.meta.elfie_id != self.elfie_id
        )
        if foreign_ids:
            raise PydanticCustomError(
                "frame_elfie_id",
                "all frame writes must share the frame elfie_id",
            )
        event_ids = tuple(write.meta.event_id for write in writes)
        if len(set(event_ids)) != len(event_ids):
            raise PydanticCustomError(
                "duplicate_frame_event_id",
                "frame write event IDs must be unique",
            )
        return self


__all__ = (
    "CoalescedSummary",
    "DroppedSummary",
    "ExecutionPayload",
    "ExecutionStatus",
    "IngestDisposition",
    "IngestReceipt",
    "InternalPayload",
    "InternalSignal",
    "PerceptionEvent",
    "PerceptionJournalEvent",
    "PerceptionFrame",
    "PerceptionMediaSample",
    "PerceptionPayload",
    "PerceptionStateUpdate",
    "PerceptionWrite",
    "PhysicalModality",
    "PhysicalPayload",
    "ProcessingFailureEvent",
    "SocialPayload",
    "TriggerReason",
)
