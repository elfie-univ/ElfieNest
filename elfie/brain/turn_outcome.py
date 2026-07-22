"""Minimal terminal evidence for one cortical turn."""

from __future__ import annotations

from enum import Enum, unique
from typing import Annotated, Optional, Tuple

from pydantic import StringConstraints, model_validator
from pydantic_core import PydanticCustomError

from elfie.message_types import (
    EventId,
    FrozenContractModel,
    PlanId,
    TurnId,
)

_NonBlankText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, pattern=r".*\S.*"),
]


@unique
class TerminalStatus(str, Enum):
    """Terminal runtime states for a cortical turn."""

    COMPLETED = "completed"
    TIMED_OUT = "timed_out"
    STALE = "stale"
    FAILED = "failed"
    CANCELLED = "cancelled"


@unique
class ModelMode(str, Enum):
    """Final model decoding mode used to produce the plan."""

    STRUCTURED = "structured"
    REPAIRED = "repaired"
    TEXT_FALLBACK = "text_fallback"
    NO_OP = "no_op"


class TurnOutcome(FrozenContractModel):
    """Stable IDs and terminal facts, intentionally excluding rich traces."""

    turn_id: TurnId
    frame_id: EventId
    plan_id: PlanId
    status: TerminalStatus
    model_mode: ModelMode
    fallback_reason: Optional[_NonBlankText]
    timeout_reason: Optional[_NonBlankText]
    stale_reason: Optional[_NonBlankText]
    error_code: Optional[_NonBlankText]
    receipt_ids: Tuple[EventId, ...]

    @model_validator(mode="after")
    def validate_terminal_reason(self) -> TurnOutcome:
        """Require the reason corresponding to exceptional terminal states."""
        if self.status is TerminalStatus.TIMED_OUT and self.timeout_reason is None:
            raise PydanticCustomError(
                "missing_timeout_reason",
                "timeout_reason is required for a timed_out outcome",
            )
        if self.status is TerminalStatus.STALE and self.stale_reason is None:
            raise PydanticCustomError(
                "missing_stale_reason",
                "stale_reason is required for a stale outcome",
            )
        if self.status is TerminalStatus.FAILED and self.error_code is None:
            raise PydanticCustomError(
                "missing_error_code",
                "error_code is required for a failed outcome",
            )
        if len(set(self.receipt_ids)) != len(self.receipt_ids):
            raise PydanticCustomError(
                "duplicate_receipt_id",
                "receipt IDs must be unique",
            )
        return self


__all__ = ("ModelMode", "TerminalStatus", "TurnOutcome")
