"""通信边界使用的不可变消息与投递回执契约。"""

from __future__ import annotations

from enum import Enum, unique
from typing import Annotated, Literal, Optional, Tuple, Union
from uuid import uuid4

from pydantic import Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

from elfie.message_types import (
    ActorRef,
    ErrorInfo,
    EventId,
    FrozenContractModel,
    IntentId,
    MediaRef,
    MessageMeta,
    UTCDateTime,
)

_NonBlank = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, pattern=r"^\S(?:.*\S)?$"),
]
_NonBlankContent = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, pattern=r".*\S.*"),
]
_Attempt = Annotated[int, Field(strict=True, ge=1)]
_Ordinal = Annotated[int, Field(strict=True, ge=0)]


@unique
class MessageDirection(str, Enum):
    """消息相对于当前精灵的流向。"""

    INBOUND = "inbound"
    OUTBOUND = "outbound"


class TextPart(FrozenContractModel):
    """普通文本消息片段。"""

    type: Literal["text"] = "text"
    text: _NonBlankContent


class ImagePart(FrozenContractModel):
    """图片引用及可选说明。"""

    type: Literal["image"] = "image"
    media: MediaRef
    caption: Optional[_NonBlankContent] = None


class AudioPart(FrozenContractModel):
    """音频引用及可选转写文本。"""

    type: Literal["audio"] = "audio"
    media: MediaRef
    transcript: Optional[_NonBlankContent] = None


class FilePart(FrozenContractModel):
    """文件引用及面向用户的文件名。"""

    type: Literal["file"] = "file"
    media: MediaRef
    filename: _NonBlank


class ReactionPart(FrozenContractModel):
    """对已有外部消息的反应。"""

    type: Literal["reaction"] = "reaction"
    target_message_id: _NonBlank
    reaction: _NonBlankContent


class SystemEventPart(FrozenContractModel):
    """平台产生的闭合系统事件。"""

    type: Literal["system_event"] = "system_event"
    event_name: _NonBlank
    description: Optional[_NonBlankContent] = None


ContentPart = Annotated[
    Union[
        TextPart,
        ImagePart,
        AudioPart,
        FilePart,
        ReactionPart,
        SystemEventPart,
    ],
    Field(discriminator="type"),
]


class DeliveryErrorInfo(ErrorInfo):
    """Typed receipt error with legacy substring lookup until Task 14."""

    def __contains__(self, needle: str) -> bool:
        return needle in self.message


class CommunicationEnvelope(FrozenContractModel):
    """跨平台、可去重并保留会话身份的完整消息。"""

    meta: MessageMeta
    account_id: _NonBlank
    channel_id: _NonBlank
    conversation_id: _NonBlank
    sender: ActorRef
    recipients: Annotated[Tuple[ActorRef, ...], Field(min_length=1)]
    direction: MessageDirection
    reply_to: Optional[_NonBlank] = None
    external_message_id: Optional[_NonBlank] = None
    dedupe_key: _NonBlank
    sequence_id: Optional[_NonBlank] = None
    ordinal: Optional[_Ordinal] = None
    parts: Annotated[Tuple[ContentPart, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_identity_and_sequence(self) -> CommunicationEnvelope:
        """Keep actor and sequence identity internally coherent."""
        if self.meta.source != self.sender:
            raise PydanticCustomError(
                "sender_identity_mismatch",
                "meta.source must equal sender",
            )
        if (self.sequence_id is None) != (self.ordinal is None):
            raise PydanticCustomError(
                "incomplete_sequence_identity",
                "sequence_id and ordinal must be provided together",
            )
        return self

    @property
    def message_id(self) -> EventId:
        """Expose the legacy message ID at the compatibility edge."""
        return self.meta.event_id

    @property
    def sender_id(self) -> str:
        """Expose the legacy sender ID at the compatibility edge."""
        return str(self.sender.actor_id)

    @property
    def recipient_id(self) -> str:
        """Expose the first legacy recipient ID."""
        return str(self.recipients[0].actor_id)

    @property
    def timestamp(self) -> float:
        """Expose the legacy Unix timestamp."""
        return self.meta.occurred_at.timestamp()


@unique
class DeliveryStatus(str, Enum):
    """A delivery lifecycle state reported by a channel boundary."""

    ACCEPTED = "accepted"
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    RETRY_SCHEDULED = "retry_scheduled"
    CANCELLED = "cancelled"


class DeliveryReceipt(FrozenContractModel):
    """Typed, correlatable result for one outbound envelope attempt."""

    receipt_id: EventId
    message_id: EventId
    channel_id: _NonBlank
    status: DeliveryStatus
    attempt: _Attempt = 1
    next_retry_at: Optional[UTCDateTime] = None
    error: Optional[ErrorInfo] = None
    intent_id: Optional[IntentId] = None

    @model_validator(mode="after")
    def validate_status_details(self) -> DeliveryReceipt:
        """Require errors and retry timestamps only for matching statuses."""
        if self.status in {
            DeliveryStatus.FAILED,
            DeliveryStatus.RETRY_SCHEDULED,
            DeliveryStatus.CANCELLED,
        } and self.error is None:
            raise PydanticCustomError(
                "missing_receipt_error",
                "terminal failure receipt requires error",
            )
        if self.status is DeliveryStatus.RETRY_SCHEDULED:
            if self.next_retry_at is None:
                raise PydanticCustomError(
                    "missing_retry_time",
                    "retry_scheduled receipt requires next_retry_at",
                )
        elif self.next_retry_at is not None:
            raise PydanticCustomError(
                "unexpected_retry_time",
                "next_retry_at is only valid for retry_scheduled",
            )
        return self

    @property
    def delivered(self) -> bool:
        """Preserve the legacy success predicate."""
        return self.status in {
            DeliveryStatus.SENT,
            DeliveryStatus.DELIVERED,
            DeliveryStatus.READ,
        }

    @classmethod
    def for_envelope(
        cls,
        envelope: CommunicationEnvelope,
        *,
        status: DeliveryStatus,
        attempt: int = 1,
        next_retry_at: Optional[UTCDateTime] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        retryable: bool = False,
        intent_id: Optional[IntentId] = None,
    ) -> DeliveryReceipt:
        """Create a receipt while retaining envelope correlation identity."""
        error = None
        if error_code is not None:
            error = DeliveryErrorInfo(
                code=error_code,
                message=error_message or error_code,
                retryable=retryable,
            )
        return cls(
            receipt_id=f"receipt_{uuid4().hex}",
            message_id=envelope.message_id,
            channel_id=envelope.channel_id,
            status=status,
            attempt=attempt,
            next_retry_at=next_retry_at,
            error=error,
            intent_id=intent_id,
        )


@unique
class InboundDispositionStatus(str, Enum):
    """Observable result of inbound validation and admission."""

    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


class InboundDisposition(FrozenContractModel):
    """Admission result without converting communication into body input."""

    message_id: EventId
    channel_id: _NonBlank
    status: InboundDispositionStatus
    error: Optional[ErrorInfo] = None


__all__ = (
    "AudioPart",
    "CommunicationEnvelope",
    "ContentPart",
    "DeliveryReceipt",
    "DeliveryStatus",
    "FilePart",
    "ImagePart",
    "InboundDisposition",
    "InboundDispositionStatus",
    "MessageDirection",
    "ReactionPart",
    "SystemEventPart",
    "TextPart",
)
