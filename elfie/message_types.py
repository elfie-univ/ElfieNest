"""Strict shared primitives for typed cross-module messages."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum, unique
from typing import Annotated, Literal, NewType, Optional, Tuple

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints
from pydantic_core import PydanticCustomError

_NonBlankId = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, pattern=r"^\S(?:.*\S)?$"),
]
_NonBlankText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, pattern=r".*\S.*"),
]
_Sha256 = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]
_SizeBytes = Annotated[int, Field(strict=True, ge=0)]

EventId = NewType("EventId", _NonBlankId)
TurnId = NewType("TurnId", _NonBlankId)
PlanId = NewType("PlanId", _NonBlankId)
IntentId = NewType("IntentId", _NonBlankId)
CommandId = NewType("CommandId", _NonBlankId)
TraceId = NewType("TraceId", _NonBlankId)
ElfieId = NewType("ElfieId", _NonBlankId)
ActorId = NewType("ActorId", _NonBlankId)
MediaId = NewType("MediaId", _NonBlankId)
CorrelationId = NewType("CorrelationId", _NonBlankId)


def _parse_utc_datetime(value: datetime) -> datetime:
    """Accept aware UTC datetimes and normalize their timezone identity."""
    offset = value.utcoffset()
    if offset is None or offset != timedelta(0):
        raise PydanticCustomError(
            "utc_datetime",
            "datetime must be timezone-aware UTC",
        )
    return value.astimezone(timezone.utc)


UTCDateTime = Annotated[datetime, AfterValidator(_parse_utc_datetime)]


class FrozenContractModel(BaseModel):
    """Base for immutable, strict, closed cross-module contracts."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


@unique
class Priority(str, Enum):
    """Scheduling priority shared by message-producing subsystems."""

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class ActorRef(FrozenContractModel):
    """Stable identity and origin category for a message actor."""

    actor_id: ActorId
    source_kind: _NonBlankText
    display_name: Optional[_NonBlankText] = None


class MediaRef(FrozenContractModel):
    """Reference to media stored outside typed message payloads."""

    media_id: MediaId
    uri: _NonBlankText
    mime_type: _NonBlankText
    size_bytes: Optional[_SizeBytes] = None
    sha256: Optional[_Sha256] = None


class ErrorInfo(FrozenContractModel):
    """Structured error details suitable for receipts and replay."""

    code: _NonBlankText
    message: _NonBlankText
    retryable: bool = False
    causes: Tuple[ErrorInfo, ...] = ()


class MessageMeta(FrozenContractModel):
    """Identity, timing, origin, and trace data shared by every message."""

    schema_version: Literal[1] = 1
    event_id: EventId
    elfie_id: ElfieId
    source: ActorRef
    occurred_at: UTCDateTime
    received_at: UTCDateTime
    trace_id: TraceId
    causation_id: Optional[EventId] = None
    correlation_id: Optional[CorrelationId] = None
    priority: Priority = Priority.NORMAL


__all__ = (
    "ActorId",
    "ActorRef",
    "CommandId",
    "CorrelationId",
    "ElfieId",
    "ErrorInfo",
    "EventId",
    "FrozenContractModel",
    "IntentId",
    "MediaId",
    "MediaRef",
    "MessageMeta",
    "PlanId",
    "Priority",
    "TraceId",
    "TurnId",
    "UTCDateTime",
)
