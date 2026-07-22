"""完整通信 envelope 的平台通道协议。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from elfie.communication.contracts import (
    CommunicationEnvelope,
    DeliveryReceipt,
)


@runtime_checkable
class CommunicationChannel(Protocol):
    """Canonical channel boundary for complete envelopes and typed receipts."""

    channel_id: str

    @property
    def is_connected(self) -> bool: ...

    def connect(self) -> bool: ...

    def disconnect(self) -> None: ...

    def send_envelope(self, envelope: CommunicationEnvelope) -> DeliveryReceipt: ...


__all__ = ("CommunicationChannel",)
