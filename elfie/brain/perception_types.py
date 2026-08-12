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


@unique
class SourceDomain(str, Enum):
    """The only three domains allowed to start a Brain turn."""

    COMMUNICATION = "communication"
    EMBODIED = "embodied"
    INTERNAL = "internal"


@unique
class ExternalExecutionDomain(str, Enum):
    """External boundaries available after deterministic decision governance."""

    COMMUNICATION = "communication"
    NERVOUS_SYSTEM = "nervous_system"


class CommunicationScope(FrozenContractModel):
    """One exact digital channel and conversation."""

    kind: Literal["communication"] = "communication"
    channel_id: _NonBlankText
    conversation_id: _NonBlankText


class EmbodiedScope(FrozenContractModel):
    """One currently observed Body identity."""

    kind: Literal["embodied"] = "embodied"
    body_id: _NonBlankText
    body_generation: _Revision = 1


class InternalScope(FrozenContractModel):
    """One receipt, failure, or internal-trigger causal chain."""

    kind: Literal["internal"] = "internal"
    cause_id: _NonBlankText


InteractionScope: TypeAlias = Annotated[
    Union[CommunicationScope, EmbodiedScope, InternalScope],
    Field(discriminator="kind"),
]


class ResponseScope(FrozenContractModel):
    """Host-owned external boundary for one immutable turn."""

    external_domain: Optional[ExternalExecutionDomain]
    channel_id: Optional[_NonBlankText] = None
    conversation_id: Optional[_NonBlankText] = None
    body_id: Optional[_NonBlankText] = None
    body_generation: Optional[_Revision] = None

    @model_validator(mode="before")
    @classmethod
    def default_embodied_generation(cls, value: object) -> object:
        """Keep legacy callers safe while making embodied scope explicit."""
        if not isinstance(value, dict):
            return value
        if (
            value.get("external_domain") is ExternalExecutionDomain.NERVOUS_SYSTEM
            or value.get("external_domain") == ExternalExecutionDomain.NERVOUS_SYSTEM.value
        ) and value.get("body_generation") is None:
            return {**value, "body_generation": 1}
        return value

    @model_validator(mode="after")
    def validate_target(self) -> ResponseScope:
        """Require exactly the target fields owned by the selected boundary."""
        if self.external_domain is ExternalExecutionDomain.COMMUNICATION:
            valid = (
                self.channel_id is not None
                and self.conversation_id is not None
                and self.body_id is None
                and self.body_generation is None
            )
        elif self.external_domain is ExternalExecutionDomain.NERVOUS_SYSTEM:
            valid = (
                self.body_id is not None
                and self.channel_id is None
                and self.conversation_id is None
                and self.body_generation is not None
            )
        else:
            valid = (
                self.channel_id is None
                and self.conversation_id is None
                and self.body_id is None
                and self.body_generation is None
            )
        if not valid:
            raise PydanticCustomError(
                "response_scope_target",
                "response scope target does not match its external domain",
            )
        return self


class PhysicalPayload(FrozenContractModel):
    """A normalized physical observation from the current Body path."""

    type: Literal["physical"]
    body_id: _NonBlankText
    body_generation: _Revision = 1
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
    body_id: _NonBlankText
    body_generation: _Revision = 1
    state_key: _NonBlankText
    revision: _Revision
    value: _StateScalar


class PerceptionMediaSample(FrozenContractModel):
    """A bounded media-stream sample that references external storage."""

    meta: MessageMeta
    body_id: _NonBlankText
    body_generation: _Revision = 1
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


class TurnFrame(FrozenContractModel):
    """An immutable, single-domain cutoff admitted for one Brain turn."""

    schema_version: Literal[1] = 1
    frame_id: EventId
    elfie_id: ElfieId
    revision: _Revision
    captured_at: UTCDateTime
    cutoff_seq: _Sequence
    trigger_reason: TriggerReason
    source_domain: SourceDomain
    interaction_scope: InteractionScope
    response_scope: ResponseScope
    events: Tuple[PerceptionJournalEvent, ...] = ()
    state_updates: Tuple[PerceptionStateUpdate, ...] = ()
    media_samples: Tuple[PerceptionMediaSample, ...] = ()
    coalesced: Tuple[CoalescedSummary, ...] = ()
    dropped: Tuple[DroppedSummary, ...] = ()

    @model_validator(mode="after")
    def validate_identity(self) -> TurnFrame:
        """Keep one identity, scope, and unique write IDs within a turn."""
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
        scope_keys = tuple(scope_key(write) for write in writes)
        expected = interaction_scope_key(self.interaction_scope)
        if any(key != expected for key in scope_keys):
            raise PydanticCustomError(
                "mixed_turn_scope",
                "all turn writes must share one interaction scope",
            )
        if domain_for_scope(self.interaction_scope) is not self.source_domain:
            raise PydanticCustomError(
                "turn_source_domain",
                "turn source domain must match its interaction scope",
            )
        if self.source_domain is SourceDomain.COMMUNICATION:
            interaction = self.interaction_scope
            if not isinstance(interaction, CommunicationScope) or (
                self.response_scope.external_domain
                is not ExternalExecutionDomain.COMMUNICATION
                or self.response_scope.channel_id != interaction.channel_id
                or self.response_scope.conversation_id != interaction.conversation_id
            ):
                raise PydanticCustomError(
                    "communication_response_scope",
                    "communication turns can respond only to their admitted conversation",
                )
        elif self.source_domain is SourceDomain.EMBODIED:
            interaction = self.interaction_scope
            if not isinstance(interaction, EmbodiedScope) or (
                self.response_scope.external_domain
                is not ExternalExecutionDomain.NERVOUS_SYSTEM
                or self.response_scope.body_id != interaction.body_id
                or self.response_scope.body_generation != interaction.body_generation
            ):
                raise PydanticCustomError(
                    "embodied_response_scope",
                    "embodied turns can respond only through their admitted body",
                )
        elif self.response_scope.external_domain is not None:
            raise PydanticCustomError(
                "internal_response_scope",
                "stage-one internal turns cannot execute an external directive",
            )
        return self


def scope_key(write: PerceptionWrite) -> Tuple[str, ...]:
    """Return the deterministic lane/scope identity for one admitted write."""
    if isinstance(write, PerceptionStateUpdate):
        return (
            SourceDomain.EMBODIED.value,
            write.body_id,
            str(write.body_generation),
        )
    if isinstance(write, PerceptionMediaSample):
        return (
            SourceDomain.EMBODIED.value,
            write.body_id,
            str(write.body_generation),
        )
    payload = write.payload
    if isinstance(payload, SocialPayload):
        return (
            SourceDomain.COMMUNICATION.value,
            payload.channel_id,
            payload.conversation_id,
        )
    if isinstance(payload, PhysicalPayload):
        return (
            SourceDomain.EMBODIED.value,
            payload.body_id,
            str(payload.body_generation),
        )
    if isinstance(payload, ExecutionPayload):
        return (SourceDomain.INTERNAL.value, f"execution:{payload.turn_id}")
    cause = write.meta.causation_id or write.meta.event_id
    return (SourceDomain.INTERNAL.value, str(cause))


def interaction_scope_for(write: PerceptionWrite) -> InteractionScope:
    """Build the typed host-owned scope for a write."""
    key = scope_key(write)
    domain = SourceDomain(key[0])
    if domain is SourceDomain.COMMUNICATION:
        return CommunicationScope(channel_id=key[1], conversation_id=key[2])
    if domain is SourceDomain.EMBODIED:
        return EmbodiedScope(
            body_id=key[1],
            body_generation=int(key[2]) if len(key) > 2 else 1,
        )
    return InternalScope(cause_id=key[1])


def interaction_scope_key(scope: InteractionScope) -> Tuple[str, ...]:
    """Return the same deterministic identity represented by a typed scope."""
    if isinstance(scope, CommunicationScope):
        return (SourceDomain.COMMUNICATION.value, scope.channel_id, scope.conversation_id)
    if isinstance(scope, EmbodiedScope):
        return (
            SourceDomain.EMBODIED.value,
            scope.body_id,
            str(scope.body_generation),
        )
    return (SourceDomain.INTERNAL.value, scope.cause_id)


def domain_for_scope(scope: InteractionScope) -> SourceDomain:
    """Return the source domain owned by an interaction scope."""
    return SourceDomain(interaction_scope_key(scope)[0])


def response_scope_for(scope: InteractionScope) -> ResponseScope:
    """Derive the maximum host-owned response boundary for a turn."""
    if isinstance(scope, CommunicationScope):
        return ResponseScope(
            external_domain=ExternalExecutionDomain.COMMUNICATION,
            channel_id=scope.channel_id,
            conversation_id=scope.conversation_id,
        )
    if isinstance(scope, EmbodiedScope):
        return ResponseScope(
            external_domain=ExternalExecutionDomain.NERVOUS_SYSTEM,
            body_id=scope.body_id,
            body_generation=scope.body_generation,
        )
    return ResponseScope(external_domain=None)


__all__ = (
    "CoalescedSummary",
    "DroppedSummary",
    "CommunicationScope",
    "EmbodiedScope",
    "ExternalExecutionDomain",
    "ExecutionPayload",
    "ExecutionStatus",
    "IngestDisposition",
    "IngestReceipt",
    "InternalPayload",
    "InternalScope",
    "InternalSignal",
    "PerceptionEvent",
    "PerceptionJournalEvent",
    "PerceptionMediaSample",
    "PerceptionPayload",
    "PerceptionStateUpdate",
    "PerceptionWrite",
    "PhysicalModality",
    "PhysicalPayload",
    "ProcessingFailureEvent",
    "ResponseScope",
    "SourceDomain",
    "SocialPayload",
    "TurnFrame",
    "TriggerReason",
    "domain_for_scope",
    "interaction_scope_for",
    "interaction_scope_key",
    "response_scope_for",
    "scope_key",
)
