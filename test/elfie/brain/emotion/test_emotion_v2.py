"""Focused tests for the six-channel signed affect model."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from elfie.brain.emotion.appraiser import EmotionAppraiser
from elfie.brain.emotion.contracts import AffectDirection, ChannelEffect
from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.emotion.emotion_types import EMOTION_NAMES, EmotionType
from elfie.brain.emotion.stimulus import EmotionStimulusEvent, StimulusSource
from elfie.brain.reasoning.decision_types import EmotionFeedback
from elfie.brain.workspace.contracts import PerceptionEvent, SocialPayload
from elfie.message_types import (
    ActorId,
    ActorRef,
    ElfieId,
    EventId,
    MessageMeta,
    TraceId,
)


def _stimulus(event_id: str, effect: ChannelEffect, *, turn_id: str | None = None):
    return EmotionStimulusEvent(
        event_id=EventId(event_id),
        effects=(effect,),
        source=StimulusSource.INTERNAL,
        turn_id=turn_id,
    )


def test_system_stores_six_absolute_channels_with_personality_visible_baselines() -> (
    None
):
    system = EmotionSystem(clock=lambda: 0.0)

    assert tuple(system.emotions) == EMOTION_NAMES
    assert all(0.0 <= value <= 1.0 for value in system.emotions.values())
    assert system.parameters("happiness").baseline > 0.0


def test_positive_drive_saturates_and_each_increment_gets_smaller() -> None:
    system = EmotionSystem(clock=lambda: 0.0)
    values = []
    for index in range(3):
        system.apply_stimulus(
            _stimulus(
                f"positive-{index}",
                ChannelEffect(
                    channel=EmotionType.FEAR,
                    direction=AffectDirection.INCREASE,
                    strength=80,
                ),
            )
        )
        values.append(system.get_emotion_value("fear"))

    increments = tuple(
        b - a
        for a, b in zip(
            (system.parameters("fear").baseline,) + tuple(values[:-1]), values
        )
    )
    assert values[0] < values[1] < values[2] < 1.0
    assert increments[0] > increments[1] > increments[2] > 0.0


def test_passive_return_has_fast_initial_drop_then_a_long_tail() -> None:
    system = EmotionSystem(clock=lambda: 0.0)
    system.apply_stimulus(
        _stimulus(
            "fear-once",
            ChannelEffect(
                channel=EmotionType.FEAR,
                direction=AffectDirection.INCREASE,
                strength=90,
            ),
        )
    )
    first = system.get_emotion_value("fear")
    system.advance_to(60.0)
    second = system.get_emotion_value("fear")
    system.advance_to(120.0)
    third = system.get_emotion_value("fear")

    assert first > second > third > system.parameters("fear").baseline
    assert first - second > second - third


def test_negative_drive_consumes_current_stock_and_equal_signed_evidence_cancels() -> (
    None
):
    system = EmotionSystem(clock=lambda: 0.0)
    system.apply_stimulus(
        _stimulus(
            "anger-once",
            ChannelEffect(
                channel=EmotionType.HAPPINESS,
                direction=AffectDirection.INCREASE,
                strength=90,
            ),
        )
    )
    before = system.get_emotion_value("happiness")
    system.apply_stimulus(
        EmotionStimulusEvent(
            event_id=EventId("anger-cancel"),
            effects=(
                ChannelEffect(
                    channel=EmotionType.HAPPINESS,
                    direction=AffectDirection.INCREASE,
                    strength=70,
                ),
                ChannelEffect(
                    channel=EmotionType.HAPPINESS,
                    direction=AffectDirection.DECREASE,
                    strength=70,
                ),
            ),
            source=StimulusSource.INTERNAL,
        )
    )
    assert system.get_emotion_value("happiness") == pytest.approx(before)

    system.apply_stimulus(
        _stimulus(
            "anger-down",
            ChannelEffect(
                channel=EmotionType.HAPPINESS,
                direction=AffectDirection.DECREASE,
                strength=60,
            ),
        )
    )
    assert 0.0 <= system.get_emotion_value("happiness") < before


def _social(content: str) -> PerceptionEvent:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return PerceptionEvent(
        meta=MessageMeta(
            event_id=EventId("social-1"),
            elfie_id=ElfieId("elfie-1"),
            source=ActorRef(actor_id=ActorId("owner-1"), source_kind="owner"),
            occurred_at=now,
            received_at=now,
            trace_id=TraceId("trace-1"),
        ),
        payload=SocialPayload(
            type="social",
            channel_id="chat",
            conversation_id="conversation",
            sender=ActorRef(actor_id=ActorId("owner-1"), source_kind="owner"),
            content=content,
        ),
        salience=0.5,
    )


def test_owner_observed_affect_is_not_elfie_affect_without_self_relevance() -> None:
    observed = EmotionAppraiser().appraise(_social("I am very sad today"))
    assert observed is not None
    assert observed.effects == ()
    assert observed.observed_other_affect is not None
    assert observed.observed_other_affect.label == "sadness"

    hostile = EmotionAppraiser().appraise(_social("I hate you, leave me alone"))
    assert hostile is not None
    assert {effect.channel for effect in hostile.effects} >= {
        EmotionType.ANGER,
        EmotionType.SADNESS,
    }
    assert any(
        effect.channel is EmotionType.HAPPINESS
        and effect.direction is AffectDirection.DECREASE
        for effect in hostile.effects
    )


def test_slow_feedback_replays_from_checkpoint_and_replaces_fast_effect() -> None:
    system = EmotionSystem(clock=lambda: 0.0)
    checkpoint = system.checkpoint()
    system.apply_stimulus(
        EmotionStimulusEvent(
            event_id=EventId("fast-turn-event"),
            effects=(
                ChannelEffect(
                    channel=EmotionType.ANGER,
                    direction=AffectDirection.INCREASE,
                    strength=95,
                ),
            ),
            source=StimulusSource.SOCIAL,
            turn_id="turn-1",
        ),
        phase="fast",
        status="provisional",
    )
    feedback = EmotionFeedback(
        effects=tuple(
            ChannelEffect(
                channel=emotion,
                direction=(
                    AffectDirection.INCREASE
                    if emotion is EmotionType.HAPPINESS
                    else AffectDirection.UNCHANGED
                ),
                strength=80 if emotion is EmotionType.HAPPINESS else 0,
            )
            for emotion in EmotionType
        )
    )
    system.reconcile_turn(
        checkpoint,
        turn_id="turn-1",
        stimulus=EmotionStimulusEvent(
            event_id=EventId("model-feedback"),
            effects=feedback.effects,
            source=StimulusSource.MODEL,
            turn_id="turn-1",
        ),
        timestamp=5.0,
    )

    assert system.get_emotion_value("anger") == pytest.approx(
        system.parameters("anger").baseline
    )
    assert (
        system.get_emotion_value("happiness") > system.parameters("happiness").baseline
    )
    statuses = {(record.phase, record.status) for record in system.effect_records()}
    assert ("slow", "replaced") in statuses
    assert ("fast", "replaced") in statuses
