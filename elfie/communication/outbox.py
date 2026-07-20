"""精灵网络消息的发送结果记录。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Dict, List, Optional

from elfie.communication.channel import CommunicationMessage


class DeliveryStatus(str, Enum):
    SENT = "sent"
    FAILED = "failed"


@dataclass(frozen=True)
class DeliveryReceipt:
    message_id: str
    channel_id: str
    status: DeliveryStatus
    error: str = ""

    @property
    def delivered(self) -> bool:
        return self.status is DeliveryStatus.SENT


@dataclass(frozen=True)
class OutboxEntry:
    message: CommunicationMessage
    receipt: DeliveryReceipt


class CommunicationOutbox:
    def __init__(self) -> None:
        self._entries: Dict[str, OutboxEntry] = {}
        self._lock = Lock()

    def record(
        self, message: CommunicationMessage, receipt: DeliveryReceipt
    ) -> OutboxEntry:
        if receipt.message_id != message.message_id:
            raise ValueError("发送回执与消息不匹配")
        entry = OutboxEntry(message=message, receipt=receipt)
        with self._lock:
            self._entries[message.message_id] = entry
        return entry

    def get(self, message_id: str) -> Optional[OutboxEntry]:
        with self._lock:
            return self._entries.get(message_id)

    @property
    def history(self) -> List[OutboxEntry]:
        with self._lock:
            return list(self._entries.values())
