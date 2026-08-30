"""Unit tests for the process-local six-channel EmotionSystem surface."""

from __future__ import annotations

from elfie.brain.emotion.contracts import (
    AffectDirection,
    AffectiveAppraisal,
    AppraisalRelevance,
    ChannelEffect,
    TrustedAppraisalScope,
)
from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.emotion.emotion_types import EMOTION_NAMES, EmotionType
from elfie.brain.emotion.stimulus import EmotionStimulusEvent, StimulusSource
from elfie.message_types import EventId


def _event(
    event_id: str,
    channel: EmotionType,
    direction: AffectDirection = AffectDirection.INCREASE,
    strength: int = 70,
) -> EmotionStimulusEvent:
    scope = TrustedAppraisalScope(
        scope_id=event_id,
        cause_event_id=EventId(event_id),
        relevance=AppraisalRelevance.DIRECT,
    )
    return EmotionStimulusEvent(
        event_id=EventId(event_id),
        appraisals=(
            AffectiveAppraisal(
                scope=scope,
                effects=(
                    ChannelEffect(
                        channel=channel,
                        direction=direction,
                        strength=strength,
                    ),
                ),
            ),
        ),
        source=StimulusSource.INTERNAL,
    )


def test_init_uses_six_normalized_absolute_stocks() -> None:
    system = EmotionSystem(clock=lambda: 0.0)

    assert tuple(system.emotions) == EMOTION_NAMES
    assert all(0.0 <= value <= 1.0 for value in system.emotions.values())
    assert all(
        system.emotions[name] == system.parameters(name).baseline
        for name in EMOTION_NAMES
    )


def test_distinct_workspace_events_accumulate_without_emotion_deduplication() -> None:
    system = EmotionSystem(clock=lambda: 0.0)

    system.apply_stimulus(_event("fear-1", EmotionType.FEAR))
    first = system.get_emotion_value("fear")
    system.apply_stimulus(_event("fear-2", EmotionType.FEAR))

    assert system.get_emotion_value("fear") > first


def test_tick_returns_each_channel_toward_its_personality_baseline() -> None:
    system = EmotionSystem(clock=lambda: 0.0)
    system.apply_stimulus(_event("anger-1", EmotionType.ANGER, strength=90))
    before = system.get_emotion_value("anger")
    baseline = system.parameters("anger").baseline

    system.tick(60.0)

    assert baseline < system.get_emotion_value("anger") < before


def test_snapshot_exposes_sparse_active_channels_without_forced_count() -> None:
    system = EmotionSystem(clock=lambda: 0.0)
    system.apply_stimulus(_event("happiness-1", EmotionType.HAPPINESS, strength=90))
    system.apply_stimulus(_event("fear-1", EmotionType.FEAR, strength=70))

    snapshot = system.snapshot(0.0)

    assert snapshot.primary is EmotionType.HAPPINESS
    assert tuple(item.name for item in snapshot.active) == (
        EmotionType.HAPPINESS,
        EmotionType.FEAR,
    )
