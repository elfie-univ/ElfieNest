"""Immutable state contracts owned by the Motivation system."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal, Optional

from pydantic import Field, StringConstraints

from elfie.message_types import EventId, FrozenContractModel, UTCDateTime

_NonBlankText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, pattern=r".*\S.*"),
]
_Revision = Annotated[int, Field(strict=True, ge=0)]
_Ratio = Annotated[float, Field(strict=True, ge=0.0, le=1.0)]


class MotivationSnapshot(FrozenContractModel):
    """Bounded fixed-drive state captured for one reasoning turn."""

    revision: _Revision
    captured_at: UTCDateTime
    recovery_pressure: _Ratio
    recovery_status: Literal["ready", "blocked", "cooldown", "satisfied", "unknown"] = (
        "unknown"
    )
    last_trigger_id: Optional[EventId] = None
    cooldown_until: Optional[UTCDateTime] = None
    satisfaction_until: Optional[UTCDateTime] = None

    @classmethod
    def unknown(cls) -> MotivationSnapshot:
        return cls(
            revision=0,
            captured_at=datetime.fromtimestamp(0, timezone.utc),
            recovery_pressure=0.0,
            recovery_status="unknown",
        )


__all__ = ("MotivationSnapshot",)
