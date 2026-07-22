"""Strict multi-intent decision contracts for the Brain output boundary."""

from __future__ import annotations

from enum import Enum, unique
from typing import Annotated, Literal, Optional, Tuple, Union

from pydantic import Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError
from typing_extensions import TypeAlias

from elfie.message_types import (
    EventId,
    FrozenContractModel,
    IntentId,
    PlanId,
    TurnId,
    UTCDateTime,
)

_NonBlankText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=8192, pattern=r".*\S.*"),
]
_Revision = Annotated[int, Field(strict=True, ge=0)]
_Intensity = Annotated[float, Field(strict=True, ge=0.0, le=1.0)]
_Ordinal = Annotated[int, Field(strict=True, ge=0)]


@unique
class CancelPolicy(str, Enum):
    """When a stale turn may cancel an intent."""

    ALWAYS = "always"
    IF_NOT_STARTED = "if_not_started"
    NEVER = "never"


@unique
class InternalOperation(str, Enum):
    """Closed internal actions accepted by the restricted internal sink."""

    REMEMBER = "remember"
    SCHEDULE = "schedule"
    REFLECT = "reflect"


class IntentContract(FrozenContractModel):
    """Fields shared by every schedulable decision intent."""

    intent_id: IntentId
    cause_event_ids: Annotated[Tuple[EventId, ...], Field(min_length=1)]
    dependency_ids: Tuple[IntentId, ...]
    deadline: UTCDateTime
    cancel_policy: CancelPolicy


class SpeechIntent(IntentContract):
    """Speech routed through NervousSystem to the current Body."""

    type: Literal["speech"]
    text: _NonBlankText


class MessageIntent(IntentContract):
    """A platform-neutral message routed through Communication."""

    type: Literal["message"]
    channel_id: _NonBlankText
    conversation_id: _NonBlankText
    content: _NonBlankText
    reply_to_event_id: Optional[EventId] = None
    sequence_id: Optional[_NonBlankText] = None
    ordinal: Optional[_Ordinal] = None
    send_after: Optional[UTCDateTime] = None

    @model_validator(mode="after")
    def validate_sequence(self) -> MessageIntent:
        """Keep optional message ordering identity complete and schedulable."""
        if (self.sequence_id is None) != (self.ordinal is None):
            raise PydanticCustomError(
                "incomplete_message_sequence",
                "sequence_id and ordinal must be provided together",
            )
        if self.send_after is not None and self.send_after > self.deadline:
            raise PydanticCustomError(
                "message_send_after",
                "send_after cannot be later than the intent deadline",
            )
        return self


class MotionIntent(IntentContract):
    """A semantic motion routed through current Body capability checks."""

    type: Literal["motion"]
    motion: _NonBlankText
    target: Optional[_NonBlankText] = None


class ExpressionIntent(IntentContract):
    """A semantic expression routed through the current Body."""

    type: Literal["expression"]
    expression: _NonBlankText
    intensity: _Intensity


class InternalIntent(IntentContract):
    """A closed internal operation routed to the restricted internal sink."""

    type: Literal["internal"]
    operation: InternalOperation
    content: _NonBlankText


class NoOpIntent(IntentContract):
    """A terminal, auditable decision that requests no external action."""

    type: Literal["noop"]
    reason: _NonBlankText


DecisionIntent: TypeAlias = Annotated[
    Union[
        SpeechIntent,
        MessageIntent,
        MotionIntent,
        ExpressionIntent,
        InternalIntent,
        NoOpIntent,
    ],
    Field(discriminator="type"),
]


class DecisionPlan(FrozenContractModel):
    """A validated dependency DAG of intents for one sealed perception frame."""

    schema_version: Literal[1] = 1
    plan_id: PlanId
    turn_id: TurnId
    frame_id: EventId
    context_revision: _Revision
    capability_revision: _Revision
    created_at: UTCDateTime
    deadline: UTCDateTime
    cause_event_ids: Annotated[Tuple[EventId, ...], Field(min_length=1)]
    intents: Annotated[Tuple[DecisionIntent, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_plan_graph(self) -> DecisionPlan:
        """Validate deadlines, causal references, and the dependency DAG."""
        if self.deadline <= self.created_at:
            raise PydanticCustomError(
                "plan_deadline",
                "plan deadline must be later than created_at",
            )
        if len(set(self.cause_event_ids)) != len(self.cause_event_ids):
            raise PydanticCustomError(
                "duplicate_cause_event",
                "plan cause event IDs must be unique",
            )

        intent_ids = tuple(intent.intent_id for intent in self.intents)
        if len(set(intent_ids)) != len(intent_ids):
            raise PydanticCustomError(
                "duplicate_intent_id",
                "intent IDs must be unique within a plan",
            )
        known_intent_ids = set(intent_ids)
        known_cause_ids = set(self.cause_event_ids)
        graph = {
            intent.intent_id: intent.dependency_ids for intent in self.intents
        }

        for intent in self.intents:
            if intent.deadline <= self.created_at or intent.deadline > self.deadline:
                raise PydanticCustomError(
                    "intent_deadline",
                    "intent deadline must be after creation and within plan deadline",
                )
            if len(set(intent.dependency_ids)) != len(intent.dependency_ids):
                raise PydanticCustomError(
                    "duplicate_dependency",
                    "intent dependency IDs must be unique",
                )
            if intent.intent_id in intent.dependency_ids:
                raise PydanticCustomError(
                    "self_dependency",
                    "an intent cannot depend on itself",
                )
            if not set(intent.dependency_ids).issubset(known_intent_ids):
                raise PydanticCustomError(
                    "unknown_dependency",
                    "intent dependency IDs must reference this plan",
                )
            if not set(intent.cause_event_ids).issubset(known_cause_ids):
                raise PydanticCustomError(
                    "unknown_cause_event",
                    "intent cause event IDs must reference plan cause events",
                )

        unresolved = set(intent_ids)
        resolved: set[IntentId] = set()
        while unresolved:
            ready = {
                intent_id
                for intent_id in unresolved
                if set(graph[intent_id]).issubset(resolved)
            }
            if not ready:
                raise PydanticCustomError(
                    "dependency_cycle",
                    "intent dependency graph contains a cycle",
                )
            unresolved.difference_update(ready)
            resolved.update(ready)
        return self


__all__ = (
    "CancelPolicy",
    "DecisionIntent",
    "DecisionPlan",
    "ExpressionIntent",
    "InternalIntent",
    "InternalOperation",
    "MessageIntent",
    "MotionIntent",
    "NoOpIntent",
    "SpeechIntent",
)
