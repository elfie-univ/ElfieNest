"""Contract tests for typed multi-intent decision plans."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import TypeAdapter, ValidationError

from elfie.brain.emotion.contracts import AffectDirection
from elfie.brain.emotion.emotion_types import EmotionType
from elfie.brain.reasoning.decision_types import (
    CancelPolicy,
    CapabilityIntent,
    DecisionIntent,
    DecisionPlan,
    EmotionFeedback,
    ExpressionIntent,
    MessageIntent,
    ModelAffectiveAppraisal,
    MotionIntent,
    NoOpIntent,
    SemanticEmotionEffect,
    SpeechIntent,
)
from elfie.message_types import EventId, IntentId, PlanId, TurnId

NOW = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)
PLAN_DEADLINE = NOW + timedelta(seconds=10)


def _message(index: int, dependency_ids: tuple[IntentId, ...]) -> MessageIntent:
    return MessageIntent(
        type="message",
        intent_id=IntentId(f"message-{index}"),
        cause_event_ids=(EventId("social-event"),),
        dependency_ids=dependency_ids,
        deadline=PLAN_DEADLINE,
        cancel_policy=CancelPolicy.IF_NOT_STARTED,
        channel_id="wechat-main",
        conversation_id="conversation-1",
        content=f"reply {index}",
    )


def _plan(intents: tuple[DecisionIntent, ...]) -> DecisionPlan:
    return DecisionPlan(
        plan_id=PlanId("plan-1"),
        turn_id=TurnId("turn-1"),
        frame_id=EventId("frame-1"),
        context_revision=3,
        capability_revision=4,
        created_at=NOW,
        deadline=PLAN_DEADLINE,
        cause_event_ids=(EventId("body-event"), EventId("social-event")),
        intents=intents,
    )


def test_plan_preserves_many_ordered_intents_when_round_tripped() -> None:
    # Given: five messages followed by physical speech, motion, and expression.
    messages = tuple(
        _message(
            index,
            () if index == 1 else (IntentId(f"message-{index - 1}"),),
        )
        for index in range(1, 6)
    )
    intents: tuple[DecisionIntent, ...] = messages + (
        SpeechIntent(
            type="speech",
            intent_id=IntentId("speech-1"),
            cause_event_ids=(EventId("body-event"),),
            dependency_ids=(),
            deadline=PLAN_DEADLINE,
            cancel_policy=CancelPolicy.IF_NOT_STARTED,
            text="hello room",
        ),
        MotionIntent(
            type="motion",
            intent_id=IntentId("motion-1"),
            cause_event_ids=(EventId("body-event"),),
            dependency_ids=(IntentId("speech-1"),),
            deadline=PLAN_DEADLINE,
            cancel_policy=CancelPolicy.ALWAYS,
            motion="walk",
            target="door",
        ),
        ExpressionIntent(
            type="expression",
            intent_id=IntentId("expression-1"),
            cause_event_ids=(EventId("social-event"),),
            dependency_ids=(),
            deadline=PLAN_DEADLINE,
            cancel_policy=CancelPolicy.IF_NOT_STARTED,
            expression="happy",
            intensity=0.8,
        ),
    )
    plan = _plan(intents)

    # When: the decision crosses a JSON boundary.
    restored = DecisionPlan.model_validate_json(plan.model_dump_json())

    # Then: ordering, variants, dependencies, and causes are unchanged.
    assert restored == plan
    assert tuple(intent.type for intent in restored.intents) == (
        "message",
        "message",
        "message",
        "message",
        "message",
        "speech",
        "motion",
        "expression",
    )
    assert restored.intents[4].dependency_ids == (IntentId("message-4"),)


def test_capability_intent_round_trips_dynamic_body_capability_and_arguments() -> None:
    intent = CapabilityIntent(
        type="capability",
        intent_id=IntentId("move-capability"),
        cause_event_ids=(EventId("body-event"),),
        dependency_ids=(),
        deadline=PLAN_DEADLINE,
        cancel_policy=CancelPolicy.ALWAYS,
        category="body",
        capability_id="body.move_to_anchor",
        arguments={"anchor_id": "home", "announce": True},
    )

    restored = TypeAdapter(DecisionIntent).validate_json(
        TypeAdapter(DecisionIntent).dump_json(intent)
    )

    assert restored == intent
    assert isinstance(restored, CapabilityIntent)
    assert restored.capability_id == "body.move_to_anchor"
    assert restored.arguments["anchor_id"] == "home"


@pytest.mark.parametrize(
    ("intents", "error"),
    [
        (
            (
                _message(1, (IntentId("message-2"),)),
                _message(2, (IntentId("message-1"),)),
            ),
            "cycle",
        ),
        ((_message(1, (IntentId("message-1"),)),), "itself"),
        ((_message(1, (IntentId("missing"),)),), "unknown"),
    ],
)
def test_plan_rejects_invalid_dependency_graph(
    intents: tuple[DecisionIntent, ...],
    error: str,
) -> None:
    # Given: a dependency graph that cannot be scheduled safely.
    # When / Then: validation fails before any router can receive the plan.
    with pytest.raises(ValidationError, match=error):
        _plan(intents)


def test_plan_rejects_cause_missing_from_frame_cause_set() -> None:
    # Given: an intent cites an event absent from the plan's sealed frame causes.
    intent = _message(1, ()).model_copy(
        update={"cause_event_ids": (EventId("unknown-event"),)}
    )

    # When / Then: cross-ID validation rejects the plan.
    with pytest.raises(ValidationError, match="cause"):
        _plan((intent,))


def test_plan_rejects_expired_intent_deadline() -> None:
    # Given: an intent whose deadline predates plan creation.
    expired = _message(1, ()).model_copy(
        update={"deadline": NOW - timedelta(seconds=1)}
    )

    # When / Then: the deadline fails before execution routing.
    with pytest.raises(ValidationError, match="deadline"):
        _plan((expired,))


def test_intent_rejects_unknown_discriminator() -> None:
    # Given: an untyped free-form action pretending to be a decision intent.
    raw = {
        "type": "teleport",
        "intent_id": "intent-1",
        "cause_event_ids": ["body-event"],
        "dependency_ids": [],
        "deadline": PLAN_DEADLINE.isoformat(),
        "cancel_policy": "always",
        "action": "bypass-capability-check",
    }

    # When / Then: the closed intent union rejects the action.
    with pytest.raises(ValidationError):
        TypeAdapter(DecisionIntent).validate_python(raw)


def test_noop_intent_discriminator_round_trips() -> None:
    intent: DecisionIntent = NoOpIntent(
        type="noop",
        intent_id=IntentId("noop-1"),
        cause_event_ids=(EventId("social-event"),),
        dependency_ids=(),
        deadline=PLAN_DEADLINE,
        cancel_policy=CancelPolicy.NEVER,
        reason="no safe external action",
    )

    adapter = TypeAdapter(DecisionIntent)
    restored = adapter.validate_json(adapter.dump_json(intent))

    assert restored == intent
    assert restored.type == "noop"


def test_plan_rejects_stale_schema_version() -> None:
    # Given: a valid plan whose serialized schema version is changed.
    plan = _plan((_message(1, ()),))
    raw = json.loads(plan.model_dump_json())
    raw["schema_version"] = 2

    # When / Then: schema drift is rejected before intent routing.
    with pytest.raises(ValidationError, match="schema_version"):
        DecisionPlan.model_validate_json(json.dumps(raw))


def test_message_intent_preserves_sequence_and_send_after() -> None:
    # Given: one message scheduled as the third item in an output sequence.
    send_after = NOW + timedelta(seconds=1)

    # When: the typed boundary parses the sequencing fields.
    intent = MessageIntent(
        type="message",
        intent_id=IntentId("message-sequenced"),
        cause_event_ids=(EventId("social-event"),),
        dependency_ids=(),
        deadline=PLAN_DEADLINE,
        cancel_policy=CancelPolicy.IF_NOT_STARTED,
        channel_id="wechat-main",
        conversation_id="conversation-1",
        content="third reply",
        sequence_id="reply-sequence",
        ordinal=2,
        send_after=send_after,
    )

    # Then: the router receives explicit ordering instead of inferring from text.
    assert intent.sequence_id == "reply-sequence"
    assert intent.ordinal == 2
    assert intent.send_after == send_after


def test_emotion_feedback_is_sparse_and_explicit_empty_is_valid() -> None:
    assert EmotionFeedback(appraisals=()).appraisals == ()
    feedback = EmotionFeedback(
        appraisals=(
            ModelAffectiveAppraisal(
                scope_id="appraisal:event-1:direct",
                effects=(
                    SemanticEmotionEffect(
                        channel=EmotionType.ANGER,
                        direction=AffectDirection.INCREASE,
                        strength=80,
                        confidence=0.9,
                    ),
                ),
            ),
        )
    )
    assert len(feedback.appraisals) == 1
    assert len(feedback.appraisals[0].effects) == 1


def test_emotion_feedback_rejects_duplicate_scope_and_observed_other_output() -> None:
    appraisal = {
        "scope_id": "appraisal:event-1:direct",
        "effects": [
            {
                "channel": "anger",
                "direction": "increase",
                "strength": 80,
                "confidence": 0.9,
            }
        ],
    }
    with pytest.raises(ValidationError, match="scope"):
        EmotionFeedback.model_validate({"appraisals": [appraisal, appraisal]})
    with pytest.raises(ValidationError, match="observed_other_affect"):
        EmotionFeedback.model_validate(
            {"appraisals": [], "observed_other_affect": "sad"}
        )
