"""通信通道协议与 Task 14 前保留的旧消息适配器。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, unique
from functools import singledispatch
from typing import Any, Callable, Dict, Mapping, Protocol, Tuple, runtime_checkable
from uuid import uuid4

from elfie.communication.contracts import (
    AudioPart,
    CommunicationEnvelope,
    ContentPart,
    DeliveryReceipt,
    FilePart,
    ImagePart,
    MessageDirection,
    ReactionPart,
    SystemEventPart,
    TextPart,
)
from elfie.message_types import ActorRef, MediaRef, MessageMeta


@unique
class MessageKind(str, Enum):
    """Legacy single-part kind retained for the compatibility adapter."""

    TEXT = "text"
    IMAGE = "image"
    EVENT = "event"


@dataclass(frozen=True, slots=True)
class CommunicationMessage:
    """Legacy single-part message accepted only at adapter edges until Task 14."""

    channel_id: str
    direction: MessageDirection
    sender_id: str
    recipient_id: str
    content: str
    kind: MessageKind = MessageKind.TEXT
    metadata: Mapping[str, Any] = field(default_factory=dict)
    message_id: str = field(default_factory=lambda: f"message_{uuid4().hex[:12]}")
    timestamp: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())

    @classmethod
    def from_envelope(cls, envelope: CommunicationEnvelope) -> CommunicationMessage:
        """Flatten one envelope for an unmigrated bool-returning channel."""
        content, kind = _legacy_content(envelope.parts[0])
        return cls(
            channel_id=envelope.channel_id,
            direction=envelope.direction,
            sender_id=envelope.sender_id,
            recipient_id=envelope.recipient_id,
            content=content,
            kind=kind,
            message_id=str(envelope.message_id),
            timestamp=envelope.timestamp,
        )

    def to_envelope(self, *, elfie_id: str | None = None) -> CommunicationEnvelope:
        """Parse the legacy shape once into canonical typed storage."""
        sender = ActorRef(actor_id=self.sender_id, source_kind="legacy_channel")
        recipient = ActorRef(actor_id=self.recipient_id, source_kind="legacy_channel")
        occurred_at = datetime.fromtimestamp(self.timestamp, timezone.utc)
        parts = _LEGACY_PART_BUILDERS[self.kind](self)
        return CommunicationEnvelope(
            meta=MessageMeta(
                event_id=self.message_id,
                elfie_id=elfie_id or self.recipient_id,
                source=sender,
                occurred_at=occurred_at,
                received_at=occurred_at,
                trace_id=f"trace-{self.message_id}",
            ),
            account_id=self.channel_id,
            channel_id=self.channel_id,
            conversation_id=self.recipient_id,
            sender=sender,
            recipients=(recipient,),
            direction=self.direction,
            dedupe_key=self.message_id,
            parts=parts,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the historical wire shape for unmigrated callers."""
        return {
            "message_id": self.message_id,
            "channel_id": self.channel_id,
            "direction": self.direction.value,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "content": self.content,
            "kind": self.kind.value,
            "metadata": dict(self.metadata),
            "timestamp": self.timestamp,
        }


@runtime_checkable
class CommunicationChannel(Protocol):
    """Canonical channel boundary for complete envelopes and typed receipts."""

    channel_id: str

    @property
    def is_connected(self) -> bool: ...

    def connect(self) -> bool: ...

    def disconnect(self) -> None: ...

    def send_envelope(self, envelope: CommunicationEnvelope) -> DeliveryReceipt: ...


@runtime_checkable
class LegacyCommunicationChannel(Protocol):
    """Temporary bool-returning channel contract removed by Task 14."""

    channel_id: str

    @property
    def is_connected(self) -> bool: ...

    def connect(self) -> bool: ...

    def disconnect(self) -> None: ...

    def send(self, message: CommunicationMessage) -> bool: ...


@singledispatch
def _legacy_content(part: ContentPart) -> Tuple[str, MessageKind]:
    raise TypeError(type(part).__name__)


@_legacy_content.register
def _legacy_text(part: TextPart) -> Tuple[str, MessageKind]:
    return part.text, MessageKind.TEXT


@_legacy_content.register
def _legacy_image(part: ImagePart) -> Tuple[str, MessageKind]:
    return part.media.uri, MessageKind.IMAGE


@_legacy_content.register
def _legacy_audio(part: AudioPart) -> Tuple[str, MessageKind]:
    return part.media.uri, MessageKind.EVENT


@_legacy_content.register
def _legacy_file(part: FilePart) -> Tuple[str, MessageKind]:
    return part.media.uri, MessageKind.EVENT


@_legacy_content.register
def _legacy_reaction(part: ReactionPart) -> Tuple[str, MessageKind]:
    return part.reaction, MessageKind.EVENT


@_legacy_content.register
def _legacy_system_event(part: SystemEventPart) -> Tuple[str, MessageKind]:
    return part.event_name, MessageKind.EVENT


def _text_parts(message: CommunicationMessage) -> Tuple[ContentPart, ...]:
    return (TextPart(text=message.content),)


def _image_parts(message: CommunicationMessage) -> Tuple[ContentPart, ...]:
    return (
        ImagePart(
            media=MediaRef(
                media_id=f"media-{message.message_id}",
                uri=message.content,
                mime_type="image/*",
            )
        ),
    )


def _event_parts(message: CommunicationMessage) -> Tuple[ContentPart, ...]:
    return (SystemEventPart(event_name=message.content),)


_LEGACY_PART_BUILDERS: Dict[
    MessageKind,
    Callable[[CommunicationMessage], Tuple[ContentPart, ...]],
] = {
    MessageKind.TEXT: _text_parts,
    MessageKind.IMAGE: _image_parts,
    MessageKind.EVENT: _event_parts,
}


__all__ = (
    "CommunicationChannel",
    "CommunicationMessage",
    "LegacyCommunicationChannel",
    "MessageDirection",
    "MessageKind",
)
