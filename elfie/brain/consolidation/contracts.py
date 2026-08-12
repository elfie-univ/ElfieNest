"""Immutable state contracts owned by the Consolidation system."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal, Optional

from pydantic import Field

from elfie.message_types import EventId, FrozenContractModel, UTCDateTime

_Revision = Annotated[int, Field(strict=True, ge=0)]


class CognitiveConsolidationSnapshot(FrozenContractModel):
    """Bounded quiet-window memory整理 state captured for one turn."""

    revision: _Revision
    captured_at: UTCDateTime
    status: Literal["ready", "blocked", "cooldown", "satisfied", "unknown"] = "unknown"
    pending_episode_count: int = Field(strict=True, ge=0)
    last_trigger_id: Optional[EventId] = None
    cooldown_until: Optional[UTCDateTime] = None
    satisfaction_until: Optional[UTCDateTime] = None
    last_run_at: Optional[UTCDateTime] = None
    last_consolidated_count: int = Field(strict=True, ge=0)
    last_knowledge_created: int = Field(strict=True, ge=0)
    last_patterns_created: int = Field(strict=True, ge=0)

    @classmethod
    def unknown(cls) -> CognitiveConsolidationSnapshot:
        return cls(
            revision=0,
            captured_at=datetime.fromtimestamp(0, timezone.utc),
            pending_episode_count=0,
            last_consolidated_count=0,
            last_knowledge_created=0,
            last_patterns_created=0,
        )


__all__ = ("CognitiveConsolidationSnapshot",)
