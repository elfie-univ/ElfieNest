"""Signed multi-channel effects replace the old fixed interaction matrix."""

from __future__ import annotations

from elfie.brain.emotion.contracts import AffectDirection, ChannelEffect
from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.emotion.emotion_types import EmotionType
from elfie.brain.emotion.stimulus import EmotionStimulusEvent, StimulusSource
from elfie.message_types import EventId


def test_one_event_can_raise_one_channel_and_directly_consume_another() -> None:
    system = EmotionSystem(clock=lambda: 0.0)
    system.apply_stimulus(
        EmotionStimulusEvent(
            event_id=EventId("baseline-happiness"),
            effects=(
                ChannelEffect(
                    channel=EmotionType.HAPPINESS,
                    direction=AffectDirection.INCREASE,
                    strength=90,
                ),
            ),
            source=StimulusSource.INTERNAL,
        )
    )
    before_happiness = system.get_emotion_value("happiness")

    system.apply_stimulus(
        EmotionStimulusEvent(
            event_id=EventId("mixed-event"),
            effects=(
                ChannelEffect(
                    channel=EmotionType.ANGER,
                    direction=AffectDirection.INCREASE,
                    strength=70,
                ),
                ChannelEffect(
                    channel=EmotionType.HAPPINESS,
                    direction=AffectDirection.DECREASE,
                    strength=60,
                ),
            ),
            source=StimulusSource.SOCIAL,
        )
    )

    assert system.get_emotion_value("anger") > system.parameters("anger").baseline
    assert system.get_emotion_value("happiness") < before_happiness


def test_equal_positive_and_negative_evidence_cancels_for_one_channel() -> None:
    system = EmotionSystem(clock=lambda: 0.0)
    system.apply_stimulus(
        EmotionStimulusEvent(
            event_id=EventId("mixed-cancel"),
            effects=(
                ChannelEffect(
                    channel=EmotionType.SADNESS,
                    direction=AffectDirection.INCREASE,
                    strength=80,
                ),
                ChannelEffect(
                    channel=EmotionType.SADNESS,
                    direction=AffectDirection.DECREASE,
                    strength=80,
                ),
            ),
            source=StimulusSource.MODEL,
        )
    )

    assert system.get_emotion_value("sadness") == system.parameters("sadness").baseline
