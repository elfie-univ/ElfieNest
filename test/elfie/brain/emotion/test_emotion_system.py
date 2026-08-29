"""Unit tests for the v1 six-channel EmotionSystem public surface."""

from __future__ import annotations

import pytest

from elfie.brain.emotion.contracts import AffectDirection, ChannelEffect
from elfie.brain.emotion.emotion_input import EmotionInput
from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.emotion.emotion_types import EMOTION_NAMES, EmotionType
from elfie.brain.emotion.stimulus import EmotionStimulusEvent, StimulusSource
from elfie.message_types import EventId


def _event(
    event_id: str,
    channel: EmotionType,
    direction: AffectDirection = AffectDirection.INCREASE,
    strength: int = 70,
    *,
    source: StimulusSource = StimulusSource.INTERNAL,
) -> EmotionStimulusEvent:
    return EmotionStimulusEvent(
        event_id=EventId(event_id),
        effects=(
            ChannelEffect(
                channel=channel,
                direction=direction,
                strength=strength,
            ),
        ),
        source=source,
    )


def test_init_uses_six_normalized_absolute_stocks() -> None:
    system = EmotionSystem(clock=lambda: 0.0)

    assert tuple(system.emotions) == EMOTION_NAMES
    assert len(system.emotions) == 6
    assert all(0.0 <= value <= 1.0 for value in system.emotions.values())
    assert all(
        system.emotions[name] == system.parameters(name).baseline
        for name in EMOTION_NAMES
    )


def test_process_input_maps_a_normalized_diagnostic_signal() -> None:
    system = EmotionSystem(clock=lambda: 0.0)
    before = system.get_emotion_value("happiness")

    change = system.process_input(EmotionInput("happiness", 0.8, "text", "input-1"))

    assert change is not None
    assert system.get_emotion_value("happiness") > before


def test_process_input_rejects_unknown_sources_and_channels() -> None:
    system = EmotionSystem(clock=lambda: 0.0)
    before = dict(system.emotions)

    assert (
        system.process_input(EmotionInput("happiness", 0.8, "audio", "audio-1")) is None
    )
    assert system.process_input(EmotionInput("unknown", 0.8, "text", "bad-1")) is None
    assert system.emotions == before


def test_signed_event_updates_multiple_channels_without_cross_channel_magic() -> None:
    system = EmotionSystem(clock=lambda: 0.0)
    system.apply_stimulus(
        EmotionStimulusEvent(
            event_id=EventId("mixed-1"),
            effects=(
                ChannelEffect(
                    channel=EmotionType.HAPPINESS,
                    direction=AffectDirection.INCREASE,
                    strength=80,
                ),
                ChannelEffect(
                    channel=EmotionType.SADNESS,
                    direction=AffectDirection.DECREASE,
                    strength=80,
                ),
            ),
            source=StimulusSource.SOCIAL,
        )
    )

    assert (
        system.get_emotion_value("happiness") > system.parameters("happiness").baseline
    )
    assert system.get_emotion_value("sadness") < system.parameters("sadness").baseline


def test_duplicate_id_is_idempotent_but_different_ids_accumulate() -> None:
    system = EmotionSystem(clock=lambda: 0.0)
    event = _event("fear-1", EmotionType.FEAR, source=StimulusSource.PHYSICAL)

    system.apply_stimulus(event)
    first = system.get_emotion_value("fear")
    assert system.apply_stimulus(event) is None
    assert system.get_emotion_value("fear") == first

    system.apply_stimulus(
        _event("fear-2", EmotionType.FEAR, source=StimulusSource.PHYSICAL)
    )
    assert system.get_emotion_value("fear") > first


def test_duplicate_id_with_changed_payload_is_a_conflict() -> None:
    system = EmotionSystem(clock=lambda: 0.0)
    system.apply_stimulus(_event("fear-1", EmotionType.FEAR, strength=40))

    with pytest.raises(ValueError, match="event id conflict"):
        system.apply_stimulus(_event("fear-1", EmotionType.FEAR, strength=90))


def test_tick_returns_each_channel_toward_its_personality_baseline() -> None:
    system = EmotionSystem(clock=lambda: 0.0)
    system.apply_stimulus(_event("anger-1", EmotionType.ANGER, strength=90))
    before = system.get_emotion_value("anger")
    baseline = system.parameters("anger").baseline

    system.tick(60.0)

    after = system.get_emotion_value("anger")
    assert baseline < after < before


def test_snapshot_exposes_primary_secondary_shares_and_trends() -> None:
    system = EmotionSystem(clock=lambda: 0.0)
    system.apply_stimulus(_event("happiness-1", EmotionType.HAPPINESS, strength=90))
    system.apply_stimulus(_event("fear-1", EmotionType.FEAR, strength=70))

    snapshot = system.snapshot(0.0)

    assert snapshot.primary == "happiness"
    assert snapshot.secondary == "fear"
    assert snapshot.primary_share > snapshot.secondary_share > 0.0
    assert dict(snapshot.trends)["happiness"] == "rising"


def test_update_emotion_is_only_a_normalized_diagnostic_adjustment() -> None:
    system = EmotionSystem(clock=lambda: 0.0)
    before = system.get_emotion_value("fear")

    change = system.update_emotion("fear", 0.5)

    assert change is not None
    assert system.get_emotion_value("fear") > before
    assert system.update_emotion("fear", 50.0) is None
