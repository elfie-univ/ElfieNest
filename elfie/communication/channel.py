"""通信消息类型和通道协议。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping, Protocol, runtime_checkable
from uuid import uuid4


class MessageDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageKind(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    EVENT = "event"


@dataclass(frozen=True)
class CommunicationMessage:
    channel_id: str
    direction: MessageDirection
    sender_id: str
    recipient_id: str
    content: str
    kind: MessageKind = MessageKind.TEXT
    metadata: Mapping[str, Any] = field(default_factory=dict)
    message_id: str = field(default_factory=lambda: f"message_{uuid4().hex[:12]}")
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
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
    channel_id: str

    @property
    def is_connected(self) -> bool: ...

    def connect(self) -> bool: ...

    def disconnect(self) -> None: ...

    def send(self, message: CommunicationMessage) -> bool: ...
