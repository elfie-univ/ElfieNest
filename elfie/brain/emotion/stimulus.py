"""Immutable multi-channel affect stimuli."""

from __future__ import annotations

from enum import Enum, unique
from typing import Annotated, Optional, Tuple

from pydantic import Field, StringConstraints

from elfie.brain.emotion.contracts import (
    AffectiveAppraisal,
)
from elfie.message_types import EventId, FrozenContractModel, TurnId

_NonBlankText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, pattern=r".*\S.*"),
]
_Dose = Annotated[float, Field(strict=True, ge=0.0, le=10.0)]


@unique
class StimulusSource(str, Enum):
    """Normalized origin classes accepted by the affect owner."""

    PHYSICAL = "physical"
    SOCIAL = "social"
    EXECUTION = "execution"
    INTERNAL = "internal"
    MODEL = "model"


class EmotionStimulusEvent(FrozenContractModel):
    """One event carrying sparse appraisals of Elfie's own state."""

    event_id: EventId
    appraisals: Annotated[
        Tuple[AffectiveAppraisal, ...], Field(min_length=1, max_length=16)
    ]
    source: StimulusSource
    dose: _Dose = 1.0
    turn_id: Optional[TurnId] = None
    cause_key: Optional[_NonBlankText] = None


__all__ = ("EmotionStimulusEvent", "StimulusSource")
