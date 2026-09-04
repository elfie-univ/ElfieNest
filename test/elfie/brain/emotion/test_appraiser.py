"""Tests for the pure perception-to-affect appraisal boundary."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from elfie.brain.emotion.appraiser import BrainClockPulse, EmotionAppraiser
from elfie.brain.emotion.contracts import (
    AffectDirection,
    AffectiveAppraisal,
    AppraisalRelevance,
    ChannelEffect,
    TrustedAppraisalScope,
)
from elfie.brain.emotion.emotion_types import EmotionType
from elfie.brain.emotion.stimulus import EmotionStimulusEvent, StimulusSource
from elfie.brain.workspace.contracts import (
    ActivityPayload,
    ActivitySignal,
    ExecutionPayload,
    ExecutionStatus,
    PerceptionEvent,
    PhysicalModality,
    PhysicalPayload,
    SocialPayload,
)
from elfie.message_types import (
    ActorId,
    ActorRef,
    ElfieId,
    ErrorInfo,
    EventId,
    IntentId,
    MessageMeta,
    PlanId,
    TraceId,
    TurnId,
)

NOW = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)


def _effects(stimulus: EmotionStimulusEvent):
    return tuple(
        effect for appraisal in stimulus.appraisals for effect in appraisal.effects
    )


def _event(payload, *, event_id: str = "impact-1", salience: float = 0.8):
    return PerceptionEvent(
        meta=MessageMeta(
            event_id=EventId(event_id),
            elfie_id=ElfieId("elfie-1"),
            source=ActorRef(actor_id=ActorId("body-1"), source_kind="body"),
            occurred_at=NOW,
            received_at=NOW,
            trace_id=TraceId("trace-1"),
        ),
        payload=payload,
        salience=salience,
    )


def _social(content: str, *, event_id: str = "social-1") -> PerceptionEvent:
    owner = ActorRef(actor_id=ActorId("owner-1"), source_kind="owner")
    return PerceptionEvent(
        meta=MessageMeta(
            event_id=EventId(event_id),
            elfie_id=ElfieId("elfie-1"),
            source=owner,
            occurred_at=NOW,
            received_at=NOW,
            trace_id=TraceId("trace-social"),
        ),
        payload=SocialPayload(
            type="social",
            channel_id="chat-main",
            conversation_id="conversation-1",
            sender=owner,
            content=content,
        ),
        salience=0.8,
    )


def test_touch_perception_emits_signed_multi_channel_effects() -> None:
    stimulus = EmotionAppraiser().appraise(
        _event(
            PhysicalPayload(
                type="physical",
                body_id="body-1",
                modality=PhysicalModality.TOUCH,
                content="impact above reflex threshold",
            )
        )
    )

    assert stimulus is not None
    assert stimulus.event_id == EventId("impact-1")
    assert stimulus.source is StimulusSource.PHYSICAL
    effects = {effect.channel: effect for effect in _effects(stimulus)}
    assert effects[EmotionType.FEAR].direction is AffectDirection.INCREASE
    assert effects[EmotionType.SURPRISE].direction is AffectDirection.INCREASE
    assert effects[EmotionType.HAPPINESS].direction is AffectDirection.DECREASE


def test_owner_affect_without_trusted_relationship_emits_no_appraisal() -> None:
    assert EmotionAppraiser().appraise(_social("I am very sad today")) is None


def test_owner_affect_can_create_sparse_empathy_under_a_trusted_scope() -> None:
    event = _social("I am very sad today")
    scope = TrustedAppraisalScope(
        scope_id="owner-empathy",
        cause_event_id=event.meta.event_id,
        relevance=AppraisalRelevance.INDIRECT,
        related_actor_id="owner-1",
        relationship_revision=4,
        relationship_weight=0.8,
    )

    stimulus = EmotionAppraiser().appraise(event, trusted_scopes=(scope,))

    assert stimulus is not None
    assert stimulus.appraisals[0].scope == scope
    assert any(effect.channel is EmotionType.SADNESS for effect in _effects(stimulus))


def test_self_relevant_hostility_emits_increase_and_decrease_channels() -> None:
    stimulus = EmotionAppraiser().appraise(_social("I hate you, leave me alone"))

    assert stimulus is not None
    effects = {(effect.channel, effect.direction) for effect in _effects(stimulus)}
    assert (EmotionType.ANGER, AffectDirection.INCREASE) in effects
    assert (EmotionType.SADNESS, AffectDirection.INCREASE) in effects
    assert (EmotionType.HAPPINESS, AffectDirection.DECREASE) in effects


def test_caring_social_signal_can_reduce_negative_stocks() -> None:
    stimulus = EmotionAppraiser().appraise(_social("Thank you, good job"))

    assert stimulus is not None
    effects = {(effect.channel, effect.direction) for effect in _effects(stimulus)}
    assert (EmotionType.HAPPINESS, AffectDirection.INCREASE) in effects
    assert (EmotionType.SADNESS, AffectDirection.DECREASE) in effects
    assert (EmotionType.FEAR, AffectDirection.DECREASE) in effects


def test_neutral_social_text_has_no_self_effect_or_observation() -> None:
    assert EmotionAppraiser().appraise(_social("The train leaves at six.")) is None


@pytest.mark.parametrize(
    ("status", "expected"),
    (
        (
            ExecutionStatus.COMPLETED,
            {(EmotionType.HAPPINESS, AffectDirection.INCREASE)},
        ),
        (
            ExecutionStatus.FAILED,
            {
                (EmotionType.SADNESS, AffectDirection.INCREASE),
                (EmotionType.ANGER, AffectDirection.INCREASE),
                (EmotionType.HAPPINESS, AffectDirection.DECREASE),
            },
        ),
    ),
)
def test_execution_receipt_emits_outcome_effects(status, expected) -> None:
    event = _event(
        ExecutionPayload(
            type="execution",
            receipt_id=EventId("receipt-1"),
            plan_id=PlanId("plan-1"),
            turn_id=TurnId("turn-1"),
            intent_id=IntentId("intent-1"),
            executor="activity",
            status=status,
            error=(
                ErrorInfo(code="test_failure", message="test failure")
                if status
                in {
                    ExecutionStatus.REJECTED,
                    ExecutionStatus.FAILED,
                    ExecutionStatus.INTERRUPTED,
                    ExecutionStatus.TIMED_OUT,
                    ExecutionStatus.CANCELLED,
                }
                else None
            ),
        ),
        event_id="execution-1",
    )

    stimulus = EmotionAppraiser().appraise(event)

    assert stimulus is not None
    actual = {(effect.channel, effect.direction) for effect in _effects(stimulus)}
    assert expected.issubset(actual)


def test_clock_and_malformed_contracts_stay_out_of_appraisal() -> None:
    pulse = BrainClockPulse(timestamp=5.0)
    clock_event = _event(
        ActivityPayload(type="activity", signal=ActivitySignal.CLOCK, detail="tick")
    )

    assert not isinstance(pulse, PerceptionEvent)
    assert EmotionAppraiser().appraise(clock_event) is None
    with pytest.raises(ValidationError):
        BrainClockPulse.model_validate({"timestamp": "5.0"})
    with pytest.raises(ValidationError):
        EmotionStimulusEvent(
            event_id=EventId("bad"),
            appraisals=(),
            source=StimulusSource.PHYSICAL,
            dose=-1.0,
        )
    with pytest.raises(ValidationError):
        EmotionStimulusEvent(
            event_id=EventId("zero-confidence"),
            appraisals=(
                AffectiveAppraisal(
                    scope=TrustedAppraisalScope(
                        scope_id="zero-confidence",
                        cause_event_id=EventId("zero-confidence"),
                        relevance=AppraisalRelevance.DIRECT,
                    ),
                    effects=(
                        ChannelEffect(
                            channel=EmotionType.FEAR,
                            direction=AffectDirection.INCREASE,
                            strength=50,
                            confidence=0.0,
                        ),
                    ),
                ),
            ),
            source=StimulusSource.PHYSICAL,
        )
