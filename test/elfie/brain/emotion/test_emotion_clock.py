"""Characterization and explicit-clock tests for emotion state."""

import pytest
from pydantic import ValidationError

from elfie.brain.emotion.accumulator.decay import decay
from elfie.brain.emotion.emotion_system import (
    EmotionSystem,
    EmotionTimeRegressionError,
)
from elfie.brain.emotion.emotion_types import EMOTION_CONFIGS, EmotionType
from elfie.brain.emotion.stimulus import EmotionStimulusEvent, StimulusSource
from elfie.message_types import EventId


def test_tick_preserves_existing_fear_decay_formula() -> None:
    # Given: fear raised above its baseline through the compatibility API.
    emotion = EmotionSystem()
    emotion.update_emotion("fear", 50.0)
    config = EMOTION_CONFIGS["fear"]

    # When: the existing relative tick advances five seconds.
    emotion.tick(5.0)

    # Then: the existing staged half-life formula is preserved exactly.
    assert emotion.get_emotion_value("fear") == pytest.approx(
        decay(
            current_value=60.0,
            dt=5.0,
            config=config,
            baseline=config["baseline"],
            half_life=config["half_life"],
        )
    )


def _replay_snapshots() -> tuple:
    emotion = EmotionSystem(clock=lambda: 0.0)
    emotion.apply_stimulus(
        EmotionStimulusEvent(
            event_id=EventId("impact-1"),
            emotion=EmotionType.FEAR,
            intensity=0.8,
            source=StimulusSource.PHYSICAL,
        )
    )
    return emotion.snapshot(5.0), emotion.snapshot(20.0)


def test_same_fake_clock_replay_produces_identical_snapshots() -> None:
    # Given / When: the same stimulus and simulation timestamps are replayed.
    first_replay = _replay_snapshots()
    second_replay = _replay_snapshots()

    # Then: values, capture instants, and revisions are byte-for-byte stable.
    assert first_replay == second_replay
    assert first_replay[0].revision < first_replay[1].revision
    assert first_replay[0].values != first_replay[1].values


def test_duplicate_stimulus_event_does_not_mutate_emotion_twice() -> None:
    # Given: one stable stimulus identity.
    emotion = EmotionSystem(clock=lambda: 0.0)
    stimulus = EmotionStimulusEvent(
        event_id=EventId("impact-1"),
        emotion=EmotionType.FEAR,
        intensity=0.8,
        source=StimulusSource.PHYSICAL,
    )

    # When: the producer retries the exact same event.
    change = emotion.apply_stimulus(stimulus)
    first = emotion.snapshot(0.0)
    duplicate_change = emotion.apply_stimulus(stimulus)
    duplicate = emotion.snapshot(0.0)

    # Then: neither values nor revision change on the duplicate.
    assert duplicate == first
    assert change is not None
    assert change.source == "physical"
    assert change.event_id == EventId("impact-1")
    assert change.previous_intensity == pytest.approx(0.1)
    assert change.current_intensity > change.previous_intensity
    assert duplicate_change is None
    assert emotion.recent_changes() == (change,)


def test_reconcile_turn_replays_baseline_then_applies_model_feedback_once() -> None:
    # Given: a pre-turn checkpoint and a fast provisional anger appraisal.
    emotion = EmotionSystem(clock=lambda: 0.0)
    checkpoint = emotion.checkpoint()
    emotion.apply_stimulus(
        EmotionStimulusEvent(
            event_id=EventId("entry-appraisal"),
            emotion=EmotionType.ANGER,
            intensity=1.0,
            source=StimulusSource.SOCIAL,
        )
    )
    assert emotion.get_emotion_value("anger") > 10.0

    # When: the model corrects the same turn to happiness at t=5.
    emotion.reconcile_turn(
        checkpoint,
        turn_id="turn-1",
        emotion=EmotionType.HAPPINESS,
        intensity=1.0,
        confidence=1.0,
        timestamp=5.0,
    )

    # Then: the provisional anger is gone, decay has been replayed, and the
    # model feedback is represented by exactly one model event.
    assert emotion.get_emotion_value("anger") == pytest.approx(10.0)
    assert emotion.get_emotion_value("happiness") > 50.0
    assert EventId("emotion-feedback:turn-1") in emotion.snapshot(5.0).source_event_ids
    assert emotion.recent_changes()[-1].source == "model"
    assert emotion.recent_changes()[-1].event_id == EventId("emotion-feedback:turn-1")


def test_wall_clock_jump_does_not_change_frequency_or_decay(monkeypatch) -> None:
    # Given: a simulation-clock-owned emotion system and one stimulus.
    emotion = EmotionSystem(clock=lambda: 10.0)
    first = EmotionStimulusEvent(
        event_id=EventId("social-1"),
        emotion=EmotionType.ATTACHMENT,
        intensity=0.5,
        source=StimulusSource.SOCIAL,
    )
    emotion.apply_stimulus(first)
    monkeypatch.setattr("time.time", lambda: 10_000_000_000.0)

    # When: only simulation time advances by one second.
    snapshot = emotion.snapshot(11.0)

    # Then: the event remains in the simulation frequency window.
    assert emotion.frequency_trackers["attachment"].get_recent_count() == 1
    assert snapshot.revision == 2


def test_emotion_advance_to_rejects_time_regression() -> None:
    # Given: emotion state advanced to a later simulation instant.
    emotion = EmotionSystem(clock=lambda: 10.0)
    emotion.advance_to(12.0)

    # When / Then: rewinding is rejected by a typed domain error.
    with pytest.raises(EmotionTimeRegressionError) as captured:
        emotion.advance_to(11.0)
    assert captured.value.previous_timestamp == 12.0
    assert captured.value.requested_timestamp == 11.0


def test_emotion_snapshot_is_immutable() -> None:
    # Given: a sealed emotion snapshot.
    snapshot = EmotionSystem(clock=lambda: 0.0).snapshot(0.0)

    # When / Then: callers cannot mutate subsystem state through it.
    with pytest.raises(ValidationError):
        snapshot.revision = 999
