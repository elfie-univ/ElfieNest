"""精灵完整出站 envelope 及类型化投递回执记录。"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Optional

from elfie.communication.contracts import (
    CommunicationEnvelope,
    DeliveryReceipt,
    DeliveryStatus,
)


@dataclass(frozen=True)
class ReceiptCorrelationError(ValueError):
    """A receipt did not identify the envelope being recorded."""

    message_id: str
    receipt_message_id: str

    def __str__(self) -> str:
        return (
            f"receipt message {self.receipt_message_id} does not match "
            f"envelope {self.message_id}"
        )


@dataclass(frozen=True)
class OutboxEntry:
    """One canonical envelope and its latest delivery receipt."""

    message: CommunicationEnvelope
    receipt: DeliveryReceipt


class CommunicationOutbox:
    """Thread-safe canonical outbound history keyed by message identity."""

    def __init__(self, *, history_capacity: int = 1024) -> None:
        self._entries: OrderedDict[str, OutboxEntry] = OrderedDict()
        self._history_capacity = history_capacity
        self._evicted_count = 0
        self._lock = Lock()

    def record(
        self,
        message: CommunicationEnvelope,
        receipt: DeliveryReceipt,
    ) -> OutboxEntry:
        """Record a receipt only when its message identity matches."""
        if receipt.message_id != message.meta.event_id:
            raise ReceiptCorrelationError(
                message_id=str(message.meta.event_id),
                receipt_message_id=str(receipt.message_id),
            )
        entry = OutboxEntry(message=message, receipt=receipt)
        with self._lock:
            message_id = str(message.meta.event_id)
            self._entries.pop(message_id, None)
            if len(self._entries) >= self._history_capacity:
                self._entries.popitem(last=False)
                self._evicted_count += 1
            self._entries[message_id] = entry
        return entry

    def get(self, message_id: str) -> Optional[OutboxEntry]:
        with self._lock:
            return self._entries.get(message_id)

    @property
    def history(self) -> list[OutboxEntry]:
        with self._lock:
            return list(self._entries.values())

    @property
    def evicted_count(self) -> int:
        with self._lock:
            return self._evicted_count


__all__ = (
    "CommunicationOutbox",
    "DeliveryReceipt",
    "DeliveryStatus",
    "OutboxEntry",
    "ReceiptCorrelationError",
)
