"""Typed facts and projections owned by the Emotion system."""

from __future__ import annotations

from enum import Enum, unique
from typing import Annotated, Literal, Optional, Tuple

from pydantic import Field, StringConstraints

from elfie.brain.emotion.emotion_types import EmotionType
from elfie.message_types import EventId, FrozenContractModel, TurnId, UTCDateTime

_NonBlankText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, pattern=r".*\S.*"),
]
_Ratio = Annotated[float, Field(strict=True, ge=0.0, le=1.0)]
_Strength = Annotated[int, Field(strict=True, ge=0, le=100)]


@unique
class AffectDirection(str, Enum):
    """Semantic direction returned by a fast or slow appraisal."""

    INCREASE = "increase"
    DECREASE = "decrease"
    UNCHANGED = "unchanged"


class ObservedOtherAffect(FrozenContractModel):
    """A cue about another actor; never an Elfie emotion mutation."""

    label: _NonBlankText
    confidence: _Ratio
    language: Optional[_NonBlankText] = None
    matched_terms: Tuple[_NonBlankText, ...] = ()


class ChannelEffect(FrozenContractModel):
    """One channel's semantic effect; programs calculate the numeric delta."""

    channel: EmotionType
    direction: AffectDirection
    strength: _Strength = 0
    confidence: _Ratio = 1.0


class AffectiveAppraisal(FrozenContractModel):
    """A complete event appraisal, including all effects the program may apply."""

    event_id: EventId
    source: _NonBlankText
    effects: Tuple[ChannelEffect, ...] = ()
    observed_other_affect: Optional[ObservedOtherAffect] = None
    cause_key: Optional[_NonBlankText] = None
    reason: Optional[_NonBlankText] = None


class EmotionValue(FrozenContractModel):
    """One named normalized absolute stock value."""

    name: _NonBlankText
    intensity: _Ratio


class EmotionSnapshot(FrozenContractModel):
    """The sole observable affect state plus a derived primary/secondary view."""

    revision: Annotated[int, Field(strict=True, ge=0)]
    captured_at: UTCDateTime
    values: Tuple[EmotionValue, ...]
    dominant: Optional[_NonBlankText] = None
    primary: Optional[_NonBlankText] = None
    secondary: Optional[_NonBlankText] = None
    primary_share: _Ratio = 0.0
    secondary_share: _Ratio = 0.0
    trends: Tuple[
        Tuple[_NonBlankText, Literal["rising", "falling", "steady"]], ...
    ] = ()
    source_event_ids: Tuple[EventId, ...] = ()
    freshness: Literal["current", "stale", "unknown"] = "current"


class EmotionChange(FrozenContractModel):
    """One bounded diagnostic record for a changed channel."""

    revision: Annotated[int, Field(strict=True, ge=0)]
    occurred_at: UTCDateTime
    event_id: EventId
    emotion: _NonBlankText
    source: _NonBlankText
    previous_intensity: _Ratio
    current_intensity: _Ratio


class EmotionEffectRecord(FrozenContractModel):
    """Bounded audit record for provisional, corrected, and fallback effects."""

    turn_id: Optional[TurnId] = None
    event_id: EventId
    phase: Literal["fast", "slow"]
    status: Literal["provisional", "replaced", "committed", "fast_unreviewed"]
    applied_at: UTCDateTime
    source: _NonBlankText
    effect_count: Annotated[int, Field(strict=True, ge=0)]
    cause_event_ids: Tuple[EventId, ...] = ()


__all__ = (
    "AffectDirection",
    "AffectiveAppraisal",
    "ChannelEffect",
    "EmotionChange",
    "EmotionEffectRecord",
    "EmotionSnapshot",
    "EmotionValue",
    "ObservedOtherAffect",
)
