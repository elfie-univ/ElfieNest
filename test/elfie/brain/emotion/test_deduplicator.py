"""Emotion intentionally trusts Workspace event admission and does not dedupe."""

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


def _event(event_id: str) -> EmotionStimulusEvent:
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
                        channel=EmotionType.FEAR,
                        direction=AffectDirection.INCREASE,
                        strength=70,
                    ),
                ),
            ),
        ),
        source=StimulusSource.PHYSICAL,
    )


def test_repeated_admitted_stimuli_refresh_the_stock_without_local_deduplication() -> (
    None
):
    system = EmotionSystem(clock=lambda: 0.0)
    event = _event("impact-1")

    system.apply_stimulus(event)
    first = system.get_emotion_value("fear")
    system.apply_stimulus(event)

    assert system.get_emotion_value("fear") > first
