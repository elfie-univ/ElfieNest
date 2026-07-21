"""精灵完整出站 envelope 及类型化投递回执记录。"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Dict, List, Optional

from elfie.communication.contracts import (
    CommunicationEnvelope,
    DeliveryReceipt,
    DeliveryStatus,
)


@dataclass(frozen=True, slots=True)
class ReceiptCorrelationError(ValueError):
    """A receipt did not identify the envelope being recorded."""

    message_id: str
    receipt_message_id: str

    def __str__(self) -> str:
        return (
            f"receipt message {self.receipt_message_id} does not match "
            f"envelope {self.message_id}"
        )


@dataclass(frozen=True, slots=True)
class OutboxEntry:
    """One canonical envelope and its latest delivery receipt."""

    message: CommunicationEnvelope
    receipt: DeliveryReceipt


class CommunicationOutbox:
    """Thread-safe canonical outbound history keyed by message identity."""

    def __init__(self) -> None:
        self._entries: Dict[str, OutboxEntry] = {}
        self._lock = Lock()

    def record(
        self,
        message: CommunicationEnvelope,
        receipt: DeliveryReceipt,
    ) -> OutboxEntry:
        """Record a receipt only when its message identity matches."""
        if receipt.message_id != message.message_id:
            raise ReceiptCorrelationError(
                message_id=str(message.message_id),
                receipt_message_id=str(receipt.message_id),
            )
        entry = OutboxEntry(message=message, receipt=receipt)
        with self._lock:
            self._entries[str(message.message_id)] = entry
        return entry

    def get(self, message_id: str) -> Optional[OutboxEntry]:
        with self._lock:
            return self._entries.get(message_id)

    @property
    def history(self) -> List[OutboxEntry]:
        with self._lock:
            return list(self._entries.values())


__all__ = (
    "CommunicationOutbox",
    "DeliveryReceipt",
    "DeliveryStatus",
    "OutboxEntry",
    "ReceiptCorrelationError",
)
