"""Sparse signed effects update one or more emotion channels."""

from __future__ import annotations

from elfie.brain.emotion.contracts import (
    AffectDirection,
    AffectiveAppraisal,
    AppraisalRelevance,
    ChannelEffect,
    TrustedAppraisalScope,
)
from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.emotion.emotion_types import EmotionType
from elfie.brain.emotion.stimulus import EmotionStimulusEvent, StimulusSource
from elfie.message_types import EventId


def _appraisal(scope_id: str, *effects: ChannelEffect) -> AffectiveAppraisal:
    return AffectiveAppraisal(
        scope=TrustedAppraisalScope(
            scope_id=scope_id,
            cause_event_id=EventId(scope_id),
            relevance=AppraisalRelevance.DIRECT,
        ),
        effects=effects,
    )


def test_one_event_can_raise_one_channel_and_directly_consume_another() -> None:
    system = EmotionSystem(clock=lambda: 0.0)
    system.apply_stimulus(
        EmotionStimulusEvent(
            event_id=EventId("baseline-happiness"),
            appraisals=(
                _appraisal(
                    "baseline-happiness",
                    ChannelEffect(
                        channel=EmotionType.HAPPINESS,
                        direction=AffectDirection.INCREASE,
                        strength=90,
                    ),
                ),
            ),
            source=StimulusSource.INTERNAL,
        )
    )
    before_happiness = system.get_emotion_value("happiness")

    system.apply_stimulus(
        EmotionStimulusEvent(
            event_id=EventId("mixed-event"),
            appraisals=(
                _appraisal(
                    "mixed-event",
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
            appraisals=(
                _appraisal(
                    "mixed-cancel-up",
                    ChannelEffect(
                        channel=EmotionType.SADNESS,
                        direction=AffectDirection.INCREASE,
                        strength=80,
                    ),
                ),
                _appraisal(
                    "mixed-cancel-down",
                    ChannelEffect(
                        channel=EmotionType.SADNESS,
                        direction=AffectDirection.DECREASE,
                        strength=80,
                    ),
                ),
            ),
            source=StimulusSource.MODEL,
        )
    )

    assert system.get_emotion_value("sadness") == system.parameters("sadness").baseline


def test_weak_parallel_signal_never_dilutes_a_strong_signal() -> None:
    strong_only = EmotionSystem(clock=lambda: 0.0)
    combined = EmotionSystem(clock=lambda: 0.0)
    strong = ChannelEffect(
        channel=EmotionType.FEAR,
        direction=AffectDirection.INCREASE,
        strength=90,
    )
    strong_only.apply_stimulus(
        EmotionStimulusEvent(
            event_id=EventId("strong-only"),
            appraisals=(_appraisal("strong-only", strong),),
            source=StimulusSource.PHYSICAL,
        )
    )
    combined.apply_stimulus(
        EmotionStimulusEvent(
            event_id=EventId("combined"),
            appraisals=(
                _appraisal("combined-strong", strong),
                _appraisal(
                    "combined-weak",
                    ChannelEffect(
                        channel=EmotionType.FEAR,
                        direction=AffectDirection.INCREASE,
                        strength=10,
                    ),
                ),
            ),
            source=StimulusSource.PHYSICAL,
        )
    )

    assert combined.get_emotion_value("fear") >= strong_only.get_emotion_value("fear")
