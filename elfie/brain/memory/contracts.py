"""Immutable read and state contracts owned by the Memory system."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal, Optional, Tuple

from pydantic import Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

from elfie.message_types import EventId, FrozenContractModel, UTCDateTime

_NonBlankText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, pattern=r".*\S.*"),
]
_Revision = Annotated[int, Field(strict=True, ge=0)]
_Ratio = Annotated[float, Field(strict=True, ge=0.0, le=1.0)]
_OptionalRatio = Optional[_Ratio]


class MemoryStateSnapshot(FrozenContractModel):
    """Versioned durable-memory projection beside retrieved excerpts."""

    revision: _Revision
    captured_at: UTCDateTime
    episodic_count: _Revision
    total_count: _Revision
    source_event_ids: Tuple[EventId, ...] = ()
    snapshot_freshness: Literal["current", "stale", "unknown"] = "current"

    @classmethod
    def unknown(cls) -> MemoryStateSnapshot:
        return cls(
            revision=0,
            captured_at=datetime.fromtimestamp(0, timezone.utc),
            episodic_count=0,
            total_count=0,
            snapshot_freshness="unknown",
        )

    @model_validator(mode="after")
    def validate_counts(self) -> MemoryStateSnapshot:
        if self.episodic_count > self.total_count:
            raise PydanticCustomError(
                "memory_state_counts",
                "episodic memory count cannot exceed total memory count",
            )
        if len(set(self.source_event_ids)) != len(self.source_event_ids):
            raise PydanticCustomError(
                "memory_state_source_identity",
                "memory state source event IDs must be unique",
            )
        if (
            self.revision == 0
            and self.total_count == 0
            and self.snapshot_freshness != "unknown"
        ):
            raise PydanticCustomError(
                "memory_state_revision",
                "revision zero memory state must be marked unknown",
            )
        return self


class MemoryItem(FrozenContractModel):
    """One typed memory excerpt with explicit causal sources."""

    memory_id: EventId
    target_kind: Literal["episode", "node", "assertion"] = "node"
    content: _NonBlankText
    relevance: _Ratio
    source_event_ids: Tuple[EventId, ...]
    importance: _Ratio = 0.5
    freshness: _Ratio = 1.0
    confidence: _OptionalRatio = None
    kind: Literal["episodic", "knowledge", "entity", "pattern"] = "episodic"
    source: Optional[str] = None


class MemoryContext(FrozenContractModel):
    """Bounded memory excerpts selected for one reasoning turn."""

    revision: _Revision
    captured_at: UTCDateTime
    items: Tuple[MemoryItem, ...]
    state: MemoryStateSnapshot = Field(default_factory=MemoryStateSnapshot.unknown)
    # Monotonic MemorySystem revision for binding a model's explicit use
    # proposal to the exact Recall snapshot that supplied its IDs.
    recall_revision: _Revision = 0

    @model_validator(mode="after")
    def validate_state_cutoff(self) -> MemoryContext:
        if self.state.captured_at > self.captured_at:
            raise PydanticCustomError(
                "memory_state_captured_at",
                "memory state cannot be newer than MemoryContext",
            )
        return self


__all__ = ("MemoryContext", "MemoryItem", "MemoryStateSnapshot")
