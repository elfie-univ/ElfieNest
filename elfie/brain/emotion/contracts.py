"""Immutable public state contracts owned by the Emotion system."""

from __future__ import annotations

from typing import Annotated, Literal, Optional, Tuple

from pydantic import Field, StringConstraints

from elfie.message_types import EventId, FrozenContractModel, UTCDateTime

_NonBlankText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, pattern=r".*\S.*"),
]
_Revision = Annotated[int, Field(strict=True, ge=0)]
_Ratio = Annotated[float, Field(strict=True, ge=0.0, le=1.0)]


class EmotionValue(FrozenContractModel):
    """One named normalized emotion value."""

    name: _NonBlankText
    intensity: _Ratio


class EmotionSnapshot(FrozenContractModel):
    """Emotion state captured by its sole Brain owner."""

    revision: _Revision
    captured_at: UTCDateTime
    values: Tuple[EmotionValue, ...]
    dominant: Optional[_NonBlankText]
    source_event_ids: Tuple[EventId, ...] = ()
    freshness: Literal["current", "stale", "unknown"] = "current"


class EmotionChange(FrozenContractModel):
    """One bounded diagnostic record for an applied affect stimulus."""

    revision: _Revision
    occurred_at: UTCDateTime
    event_id: EventId
    emotion: _NonBlankText
    source: _NonBlankText
    previous_intensity: _Ratio
    current_intensity: _Ratio


__all__ = ("EmotionChange", "EmotionSnapshot", "EmotionValue")
