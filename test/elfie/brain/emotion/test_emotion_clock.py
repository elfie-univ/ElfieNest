"""Simulation-clock and replay guarantees for the affect owner."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from elfie.brain.emotion.contracts import (
    AffectDirection,
    AffectiveAppraisal,
    AppraisalRelevance,
    ChannelEffect,
    TrustedAppraisalScope,
)
from elfie.brain.emotion.emotion_system import (
    EmotionSystem,
    EmotionTimeRegressionError,
)
from elfie.brain.emotion.emotion_types import EmotionType
from elfie.brain.emotion.stimulus import EmotionStimulusEvent, StimulusSource
from elfie.message_types import EventId


def _stimulus(
    event_id: str, channel: EmotionType, strength: int
) -> EmotionStimulusEvent:
    return EmotionStimulusEvent(
        event_id=EventId(event_id),
        appraisals=(
            AffectiveAppraisal(
                scope=TrustedAppraisalScope(
                    scope_id=event_id,
                    cause_event_id=EventId(event_id),
                    relevance=AppraisalRelevance.DIRECT,
                ),
                effects=(
                    ChannelEffect(
                        channel=channel,
                        direction=AffectDirection.INCREASE,
                        strength=strength,
                    ),
                ),
            ),
        ),
        source=StimulusSource.PHYSICAL,
    )


def test_passive_return_has_a_fast_initial_drop_and_long_tail() -> None:
    system = EmotionSystem(clock=lambda: 0.0)
    system.apply_stimulus(_stimulus("fear-1", EmotionType.FEAR, 90))
    first = system.get_emotion_value("fear")
    system.advance_to(60.0)
    second = system.get_emotion_value("fear")
    system.advance_to(120.0)
    third = system.get_emotion_value("fear")
    baseline = system.parameters("fear").baseline

    assert first > second > third > baseline
    assert first - second > second - third


def test_time_regression_is_rejected() -> None:
    system = EmotionSystem(clock=lambda: 10.0)
    system.advance_to(12.0)

    with pytest.raises(EmotionTimeRegressionError):
        system.advance_to(11.0)


def test_replay_at_identical_timestamps_is_deterministic() -> None:
    def replay():
        system = EmotionSystem(clock=lambda: 0.0)
        system.apply_stimulus(_stimulus("fear-1", EmotionType.FEAR, 80))
        return system.snapshot(5.0), system.snapshot(20.0)

    assert replay() == replay()


def test_sleep_reset_starts_a_new_process_local_emotion_epoch() -> None:
    system = EmotionSystem(clock=lambda: 0.0)
    system.apply_stimulus(_stimulus("fear-1", EmotionType.FEAR, 80))
    previous_epoch = system.lifecycle_epoch

    system.reset_to_baseline(5.0)

    assert system.lifecycle_epoch == previous_epoch + 1
    assert system.get_emotion_value("fear") == system.parameters("fear").baseline


def test_snapshot_contract_is_immutable() -> None:
    snapshot = EmotionSystem(clock=lambda: 0.0).snapshot(0.0)

    with pytest.raises(ValidationError):
        snapshot.revision = 999
