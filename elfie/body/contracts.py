"""Strict contracts crossing the Body boundary."""

from __future__ import annotations

from enum import Enum, unique
from typing import Annotated, Literal, Mapping, NewType, Optional, Tuple, Union
from uuid import uuid4

from pydantic import Field, JsonValue, StringConstraints, model_validator
from pydantic_core import PydanticCustomError
from typing_extensions import TypeAlias

from elfie.message_types import (
    ActorRef,
    CommandId,
    ErrorInfo,
    EventId,
    FrozenContractModel,
    IntentId,
    MediaRef,
    TurnId,
    UTCDateTime,
)

_NonBlankText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, pattern=r".*\S.*"),
]
_PositiveDimension = Annotated[int, Field(strict=True, gt=0)]
_ObservationCount = Annotated[int, Field(strict=True, ge=1, le=64)]
_NonNegativeFloat = Annotated[float, Field(strict=True, ge=0)]
_Ratio = Annotated[float, Field(strict=True, ge=0, le=1)]
_Revision = Annotated[int, Field(strict=True, ge=1)]
_Generation = Annotated[int, Field(strict=True, ge=1)]

BodyId = NewType("BodyId", _NonBlankText)


class UtteranceFinal(FrozenContractModel):
    kind: Literal["utterance_final"]
    text: _NonBlankText
    language: Optional[_NonBlankText] = None
    confidence: Optional[_Ratio] = None
    audio: Optional[MediaRef] = None


class VisionSample(FrozenContractModel):
    kind: Literal["vision_sample"]
    media: MediaRef
    width_px: Optional[_PositiveDimension] = None
    height_px: Optional[_PositiveDimension] = None


class VisionChange(FrozenContractModel):
    kind: Literal["vision_change"]
    description: _NonBlankText
    media: Optional[MediaRef] = None


class TactileImpact(FrozenContractModel):
    kind: Literal["tactile_impact"]
    location: _NonBlankText
    intensity: _Ratio = 0.0
    direction: _NonBlankText = "none"
    contact_kind: _NonBlankText = "world"
    source_semantic_id: Optional[_NonBlankText] = None
    force_newtons: Optional[_NonNegativeFloat] = None


class ProprioceptionSample(FrozenContractModel):
    kind: Literal["proprioception_sample"]
    posture: _NonBlankText
    target: Optional[_NonBlankText] = None
    zone_id: Optional[_NonBlankText] = None
    active_command_id: Optional[_NonBlankText] = None
    arrived: bool = False


class ActionOutcomePayload(FrozenContractModel):
    """One terminal Body action outcome re-entering the perception path."""

    kind: Literal["action_outcome"]
    command_id: _NonBlankText
    intent_id: _NonBlankText
    status: Literal[
        "completed",
        "rejected",
        "failed",
        "interrupted",
        "timed_out",
    ]
    reason: Optional[_NonBlankText] = None


class EnvironmentSample(FrozenContractModel):
    kind: Literal["environment_sample"]
    temperature_celsius: Optional[float] = None
    humidity_ratio: Optional[_Ratio] = None
    illuminance_lux: Optional[_NonNegativeFloat] = None


class HeardUtterancePayload(FrozenContractModel):
    """Structured virtual-hearing fact delivered to one Elfie."""

    kind: Literal["heard_utterance"]
    utterance_id: _NonBlankText
    sender_id: _NonBlankText
    text: _NonBlankText
    emotion: Optional[_NonBlankText] = None


class SemanticVisualEntityPayload(FrozenContractModel):
    """One Nest-resolved semantic referent in a visual scene."""

    semantic_id: _NonBlankText
    kind: Literal["actor", "anchor", "facility"]
    zone_id: _NonBlankText
    label: _NonBlankText
    capabilities: Tuple[_NonBlankText, ...] = ()


class SemanticVisualScenePayload(FrozenContractModel):
    """Structured, bounded semantic vision delivered to one Elfie."""

    kind: Literal["semantic_visual_scene"]
    observation_id: _NonBlankText
    observer_id: _NonBlankText
    zone_id: _NonBlankText
    entities: Tuple[SemanticVisualEntityPayload, ...] = ()


class SemanticActionResultPayload(FrozenContractModel):
    """Structured result of one Nest-resolved semantic action."""

    kind: Literal["semantic_action_result"]
    command_id: _NonBlankText
    intent_id: _NonBlankText
    actor_id: _NonBlankText
    body_generation: _Generation
    target: _NonBlankText
    resolved_anchor_id: _NonBlankText
    status: Literal["completed", "failed", "cancelled", "timed_out"]
    reason: Optional[_NonBlankText] = None


class NestFactNoticePayload(FrozenContractModel):
    """Structured semantic notice from a Nest owner other than interaction."""

    kind: Literal["nest_fact_notice"]
    fact_type: Literal[
        "facility_state_changed",
        "home_assignment_changed",
        "environment_phase_changed",
        "environment_desired_changed",
        "environment_rule_changed",
    ]
    fact_id: _NonBlankText
    summary: _NonBlankText
    zone_id: Optional[_NonBlankText] = None
    active: Optional[bool] = None
    lights_on: Optional[bool] = None
    quiet_mode: Optional[bool] = None
    phase: Optional[_NonBlankText] = None


SensorPayload: TypeAlias = Annotated[
    Union[
        UtteranceFinal,
        VisionSample,
        VisionChange,
        TactileImpact,
        ProprioceptionSample,
        ActionOutcomePayload,
        EnvironmentSample,
        HeardUtterancePayload,
        SemanticVisualScenePayload,
        SemanticActionResultPayload,
        NestFactNoticePayload,
    ],
    Field(discriminator="kind"),
]


class BodySensorEvent(FrozenContractModel):
    event_id: EventId
    cause_id: Optional[EventId] = None
    body_id: BodyId
    body_generation: _Generation = 1
    source: ActorRef
    occurred_at: UTCDateTime
    received_at: UTCDateTime
    payload: SensorPayload


class _CommandBase(FrozenContractModel):
    command_id: CommandId
    turn_id: TurnId
    intent_id: IntentId
    body_id: BodyId
    issued_at: UTCDateTime
    deadline: UTCDateTime
    capability_revision: _Revision
    body_generation: _Generation = 1

    @model_validator(mode="after")
    def deadline_follows_issue_time(self) -> _CommandBase:
        if self.deadline < self.issued_at:
            raise PydanticCustomError(
                "invalid_deadline",
                "deadline must not precede issued_at",
            )
        return self


class SpeechCommand(_CommandBase):
    command_type: Literal["speech"]
    text: _NonBlankText
    voice: Optional[_NonBlankText] = None
    audio: Optional[MediaRef] = None


class MotionCommand(_CommandBase):
    command_type: Literal["motion"]
    kind: _NonBlankText
    target: Optional[_NonBlankText] = None
    posture: Optional[_NonBlankText] = None


class ExpressionCommand(_CommandBase):
    command_type: Literal["expression"]
    kind: _NonBlankText
    intensity: Optional[_Ratio] = None


class EmergencyStopCommand(_CommandBase):
    command_type: Literal["emergency_stop"]
    reason: _NonBlankText


class ObservationCommand(_CommandBase):
    """Request one bounded semantic observation through the active Body path."""

    command_type: Literal["observation"]
    observation_id: _NonBlankText
    max_results: _ObservationCount = 32


class CapabilityCommand(_CommandBase):
    """Carry a registered Body capability without fixing its future vocabulary."""

    command_type: Literal["capability"]
    capability_id: _NonBlankText
    arguments: Mapping[str, JsonValue] = Field(default_factory=dict)


BodyCommand: TypeAlias = Annotated[
    Union[
        SpeechCommand,
        MotionCommand,
        ExpressionCommand,
        EmergencyStopCommand,
        ObservationCommand,
        CapabilityCommand,
    ],
    Field(discriminator="command_type"),
]


@unique
class CommandStatus(str, Enum):
    ACCEPTED = "accepted"
    STARTED = "started"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    TIMED_OUT = "timed_out"


class CommandReceipt(FrozenContractModel):
    receipt_id: EventId
    cause_id: Optional[EventId] = None
    command_id: CommandId
    turn_id: TurnId
    intent_id: IntentId
    body_id: BodyId
    status: CommandStatus
    occurred_at: UTCDateTime
    capability_revision: _Revision
    body_generation: _Generation = 1
    error: Optional[ErrorInfo] = None

    @model_validator(mode="after")
    def error_matches_status(self) -> CommandReceipt:
        successful = self.status in {
            CommandStatus.ACCEPTED,
            CommandStatus.STARTED,
            CommandStatus.COMPLETED,
        }
        if successful and self.error is not None:
            raise PydanticCustomError(
                "unexpected_receipt_error",
                "successful lifecycle receipt cannot contain an error",
            )
        if not successful and self.error is None:
            raise PydanticCustomError(
                "missing_receipt_error",
                "terminal failure receipt requires ErrorInfo",
            )
        return self

    @classmethod
    def for_status(
        cls,
        command: BodyCommand,
        status: CommandStatus,
        *,
        occurred_at: UTCDateTime,
        error: ErrorInfo | None = None,
    ) -> CommandReceipt:
        return cls(
            receipt_id=EventId(f"receipt_{uuid4().hex}"),
            command_id=command.command_id,
            turn_id=command.turn_id,
            intent_id=command.intent_id,
            body_id=command.body_id,
            status=status,
            occurred_at=occurred_at,
            capability_revision=command.capability_revision,
            body_generation=command.body_generation,
            error=error,
        )

    @classmethod
    def completed(
        cls,
        command: BodyCommand,
        *,
        occurred_at: UTCDateTime,
    ) -> CommandReceipt:
        return cls.for_status(
            command,
            CommandStatus.COMPLETED,
            occurred_at=occurred_at,
        )


class BodySnapshot(FrozenContractModel):
    body_id: BodyId
    captured_at: UTCDateTime
    connected: bool
    capability_revision: _Revision
    body_generation: _Generation = 1
    pending_event_count: Annotated[int, Field(strict=True, ge=0)] = 0
    last_command_id: Optional[CommandId] = None
    last_status: Optional[CommandStatus] = None


__all__ = (
    "BodyCommand",
    "BodyId",
    "BodySensorEvent",
    "BodySnapshot",
    "ActionOutcomePayload",
    "CapabilityCommand",
    "CommandReceipt",
    "CommandStatus",
    "EmergencyStopCommand",
    "EnvironmentSample",
    "ExpressionCommand",
    "HeardUtterancePayload",
    "MotionCommand",
    "NestFactNoticePayload",
    "ObservationCommand",
    "ProprioceptionSample",
    "SemanticActionResultPayload",
    "SemanticVisualEntityPayload",
    "SemanticVisualScenePayload",
    "SensorPayload",
    "SpeechCommand",
    "TactileImpact",
    "UtteranceFinal",
    "VisionChange",
    "VisionSample",
)
