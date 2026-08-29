"""Immutable coordinator-owned emotion stimulus contract."""

from enum import Enum, unique
from typing import Annotated

from pydantic import Field

from elfie.brain.emotion.emotion_types import EmotionType
from elfie.message_types import EventId, FrozenContractModel

_Intensity = Annotated[float, Field(strict=True, ge=0.0, le=1.0)]


@unique
class StimulusSource(str, Enum):
    """Normalized origin classes accepted by the limbic system."""

    PHYSICAL = "physical"
    SOCIAL = "social"
    EXECUTION = "execution"
    MODEL = "model"


class EmotionStimulusEvent(FrozenContractModel):
    """One deduplicable emotion stimulus produced by EmotionAppraiser."""

    event_id: EventId
    emotion: EmotionType
    intensity: _Intensity
    source: StimulusSource


__all__ = ("EmotionStimulusEvent", "StimulusSource")
