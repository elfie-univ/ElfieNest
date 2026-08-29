"""Event identity behavior now owned by EmotionSystem."""

from __future__ import annotations

import pytest

from elfie.brain.emotion.contracts import AffectDirection, ChannelEffect
from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.emotion.emotion_types import EmotionType
from elfie.brain.emotion.stimulus import EmotionStimulusEvent, StimulusSource
from elfie.message_types import EventId


def _event(event_id: str, strength: int = 70) -> EmotionStimulusEvent:
    return EmotionStimulusEvent(
        event_id=EventId(event_id),
        effects=(
            ChannelEffect(
                channel=EmotionType.FEAR,
                direction=AffectDirection.INCREASE,
                strength=strength,
            ),
        ),
        source=StimulusSource.PHYSICAL,
    )


def test_same_event_id_is_applied_once_without_frequency_deduplication() -> None:
    system = EmotionSystem(clock=lambda: 0.0)

    system.apply_stimulus(_event("impact-1"))
    first = system.get_emotion_value("fear")
    system.apply_stimulus(_event("impact-1"))

    assert system.get_emotion_value("fear") == first
    assert len(system.effect_records()) == 1


def test_repeated_distinct_events_continue_to_refresh_the_stock() -> None:
    system = EmotionSystem(clock=lambda: 0.0)

    system.apply_stimulus(_event("impact-1"))
    first = system.get_emotion_value("fear")
    system.apply_stimulus(_event("impact-2"))

    assert system.get_emotion_value("fear") > first
    assert len(system.effect_records()) == 2


def test_reusing_an_event_id_with_different_payload_is_rejected() -> None:
    system = EmotionSystem(clock=lambda: 0.0)
    system.apply_stimulus(_event("impact-1", strength=40))

    with pytest.raises(ValueError, match="event id conflict"):
        system.apply_stimulus(_event("impact-1", strength=90))
