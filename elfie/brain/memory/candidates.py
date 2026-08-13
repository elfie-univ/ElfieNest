"""Explicit Memory-owned candidates produced by one admitted Turn."""

from __future__ import annotations

from typing import Annotated, Tuple

from pydantic import Field, StringConstraints

from elfie.message_types import EventId, FrozenContractModel, UTCDateTime

_NonBlankText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=8192, pattern=r".*\S.*"),
]


class EpisodicMemoryCandidate(FrozenContractModel):
    """One reviewable proposal to encode a subjective episodic memory."""

    candidate_id: EventId
    base_revision: Annotated[int, Field(strict=True, ge=0)]
    content: _NonBlankText
    emotion: _NonBlankText
    intensity: Annotated[float, Field(strict=True, ge=0.0, le=100.0)]
    stimulus: _NonBlankText
    source_event_ids: Tuple[EventId, ...] = Field(min_length=1)
    created_at: UTCDateTime


__all__ = ("EpisodicMemoryCandidate",)
