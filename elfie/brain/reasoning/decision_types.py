"""Strict multi-intent decision contracts for the Brain output boundary."""

from __future__ import annotations

from enum import Enum, unique
from typing import Annotated, Literal, Optional, Tuple, Union

from pydantic import Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError
from typing_extensions import TypeAlias

from elfie.brain.activity.system import (
    ActivityDraft,
    ActivityPreflightResult,
    ActivityPreflightStatus,
)
from elfie.brain.emotion.contracts import AffectDirection
from elfie.brain.emotion.emotion_types import EmotionType
from elfie.brain.workspace.contracts import (
    CommunicationScope,
    EmbodiedScope,
    ExternalExecutionDomain,
    InteractionScope,
    ResponseScope,
    SourceDomain,
)
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
_SemanticStrength = Annotated[int, Field(strict=True, ge=1, le=100)]
_Confidence = Annotated[float, Field(strict=True, gt=0.0, le=1.0)]


@unique
class CancelPolicy(str, Enum):
    """When a stale turn may cancel an intent."""

    ALWAYS = "always"
    IF_NOT_STARTED = "if_not_started"
    NEVER = "never"


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


class PersistentActivityRequest(IntentContract):
    """A draft proposed by the model and validated inside its ReasoningRun."""

    type: Literal["activity"]
    draft: ActivityDraft
    preflight: Optional[ActivityPreflightResult] = None


class NoOpIntent(IntentContract):
    """A terminal, auditable decision that requests no external action."""

    type: Literal["noop"]
    reason: _NonBlankText


class SemanticEmotionEffect(FrozenContractModel):
    """One non-zero semantic effect proposed by the model."""

    channel: EmotionType
    direction: AffectDirection
    strength: _SemanticStrength
    confidence: _Confidence


class ModelAffectiveAppraisal(FrozenContractModel):
    """Sparse effects selected for one host-signed appraisal scope."""

    scope_id: _NonBlankText
    effects: Annotated[
        Tuple[SemanticEmotionEffect, ...],
        Field(min_length=1, max_length=6),
    ]

    @model_validator(mode="after")
    def validate_unique_channels(self) -> ModelAffectiveAppraisal:
        channels = tuple(effect.channel for effect in self.effects)
        if len(channels) != len(set(channels)):
            raise PydanticCustomError(
                "duplicate_model_appraisal_channel",
                "one model appraisal may affect each channel at most once",
            )
        return self


class EmotionFeedback(FrozenContractModel):
    """Model-reviewed sparse appraisals; an empty tuple is an explicit no-op."""

    appraisals: Annotated[Tuple[ModelAffectiveAppraisal, ...], Field(max_length=16)]

    @model_validator(mode="after")
    def validate_unique_scopes(self) -> EmotionFeedback:
        scope_ids = tuple(appraisal.scope_id for appraisal in self.appraisals)
        if len(scope_ids) != len(set(scope_ids)):
            raise PydanticCustomError(
                "duplicate_model_appraisal_scope",
                "emotion feedback may select each host scope at most once",
            )
        return self


DecisionIntent: TypeAlias = Annotated[
    Union[
        SpeechIntent,
        MessageIntent,
        MotionIntent,
        ExpressionIntent,
        PersistentActivityRequest,
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
    emotion_feedback: Optional[EmotionFeedback] = None

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
        graph = {intent.intent_id: intent.dependency_ids for intent in self.intents}

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


class TurnDecision(FrozenContractModel):
    """One host-scoped final decision accepted for a single-domain turn."""

    source_domain: SourceDomain
    interaction_scope: InteractionScope
    response_scope: ResponseScope
    plan: DecisionPlan

    @model_validator(mode="after")
    def validate_response_boundary(self) -> TurnDecision:
        """Reject model intents that expand the admitted turn boundary."""
        for intent in self.plan.intents:
            if isinstance(intent, PersistentActivityRequest) and (
                intent.preflight is None
                or intent.preflight.activity_id != intent.draft.activity_id
                or intent.preflight.status is not ActivityPreflightStatus.VALIDATED
            ):
                raise PydanticCustomError(
                    "activity_preflight_missing",
                    "Activity requests require validated same-run Preflight evidence",
                )
        if self.source_domain is SourceDomain.COMMUNICATION:
            scope = self.interaction_scope
            if not isinstance(scope, CommunicationScope) or (
                self.response_scope.external_domain
                is not ExternalExecutionDomain.COMMUNICATION
                or self.response_scope.channel_id != scope.channel_id
                or self.response_scope.conversation_id != scope.conversation_id
            ):
                raise PydanticCustomError(
                    "decision_interaction_scope",
                    "communication decision requires its admitted conversation scope",
                )
            for intent in self.plan.intents:
                if isinstance(intent, MessageIntent):
                    if (
                        intent.channel_id != scope.channel_id
                        or intent.conversation_id != scope.conversation_id
                    ):
                        raise PydanticCustomError(
                            "decision_conversation_scope",
                            "communication decision target exceeds the admitted conversation",
                        )
                elif not isinstance(intent, (PersistentActivityRequest, NoOpIntent)):
                    raise PydanticCustomError(
                        "decision_external_domain",
                        "communication turns cannot produce nervous-system intents",
                    )
        elif self.source_domain is SourceDomain.EMBODIED:
            scope = self.interaction_scope
            if not isinstance(scope, EmbodiedScope) or (
                self.response_scope.external_domain
                is not ExternalExecutionDomain.NERVOUS_SYSTEM
                or self.response_scope.body_id != scope.body_id
                or self.response_scope.body_generation != scope.body_generation
            ):
                raise PydanticCustomError(
                    "decision_interaction_scope",
                    "embodied decision requires its admitted body scope",
                )
            if any(isinstance(intent, MessageIntent) for intent in self.plan.intents):
                raise PydanticCustomError(
                    "decision_external_domain",
                    "embodied turns cannot produce communication intents",
                )
        else:
            scope = self.interaction_scope
            allowed_scope = getattr(scope, "response_scope", None)
            expected_scope = allowed_scope or ResponseScope(external_domain=None)
            if self.response_scope != expected_scope:
                raise PydanticCustomError(
                    "decision_interaction_scope",
                    "internal decisions cannot exceed their trigger response scope",
                )
            if self.response_scope.external_domain is None and any(
                isinstance(
                    intent,
                    (SpeechIntent, MessageIntent, MotionIntent, ExpressionIntent),
                )
                for intent in self.plan.intents
            ):
                raise PydanticCustomError(
                    "decision_external_domain",
                    "internal turns without an allowed scope cannot produce external intents",
                )
            if (
                self.response_scope.external_domain
                is ExternalExecutionDomain.COMMUNICATION
                and any(
                    isinstance(intent, (SpeechIntent, MotionIntent, ExpressionIntent))
                    for intent in self.plan.intents
                )
            ):
                raise PydanticCustomError(
                    "decision_external_domain",
                    "communication-scoped internal turns cannot produce body intents",
                )
            if (
                self.response_scope.external_domain
                is ExternalExecutionDomain.NERVOUS_SYSTEM
                and any(
                    isinstance(intent, MessageIntent) for intent in self.plan.intents
                )
            ):
                raise PydanticCustomError(
                    "decision_external_domain",
                    "body-scoped internal turns cannot produce communication intents",
                )
        return self


__all__ = (
    "CancelPolicy",
    "DecisionIntent",
    "DecisionPlan",
    "EmotionFeedback",
    "ExpressionIntent",
    "MessageIntent",
    "MotionIntent",
    "ModelAffectiveAppraisal",
    "NoOpIntent",
    "PersistentActivityRequest",
    "SpeechIntent",
    "SemanticEmotionEffect",
    "TurnDecision",
)
