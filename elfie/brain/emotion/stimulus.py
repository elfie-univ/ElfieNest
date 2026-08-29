"""Immutable multi-channel affect stimuli."""

from __future__ import annotations

from enum import Enum, unique
from typing import Annotated, Optional, Tuple

from pydantic import Field, StringConstraints

from elfie.brain.emotion.contracts import (
    AffectiveAppraisal,
    ChannelEffect,
    ObservedOtherAffect,
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
    TEXT = "text"
    SOCIAL = "social"
    EXECUTION = "execution"
    INTERNAL = "internal"
    MODEL = "model"


class EmotionStimulusEvent(FrozenContractModel):
    """One event carrying zero or more signed channel effects."""

    event_id: EventId
    effects: Tuple[ChannelEffect, ...]
    source: StimulusSource
    dose: _Dose = 1.0
    turn_id: Optional[TurnId] = None
    cause_key: Optional[_NonBlankText] = None
    observed_other_affect: Optional[ObservedOtherAffect] = None

    @classmethod
    def from_appraisal(
        cls,
        appraisal: AffectiveAppraisal,
        *,
        dose: float = 1.0,
        turn_id: TurnId | None = None,
    ) -> EmotionStimulusEvent:
        return cls(
            event_id=appraisal.event_id,
            effects=appraisal.effects,
            source=StimulusSource(appraisal.source),
            dose=dose,
            turn_id=turn_id,
            cause_key=appraisal.cause_key,
            observed_other_affect=appraisal.observed_other_affect,
        )


__all__ = ("EmotionStimulusEvent", "StimulusSource")
