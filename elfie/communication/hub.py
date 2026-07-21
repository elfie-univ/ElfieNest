"""一只精灵独立拥有的类型化网络消息通信中心。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Sequence, Tuple, TypedDict

from elfie.communication.channel import (
    CommunicationMessage,
    MessageDirection,
    MessageKind,
)
from elfie.communication.contracts import (
    CommunicationEnvelope,
    DeliveryReceipt,
    DeliveryStatus,
    InboundDisposition,
    InboundDispositionStatus,
)
from elfie.communication.inbox import CommunicationInbox
from elfie.communication.outbox import CommunicationOutbox
from elfie.communication.policy import CommunicationPolicy, CommunicationPolicyError
from elfie.communication.router import CommunicationRouter, RegisteredChannel
from elfie.message_types import ErrorInfo


class ChannelSnapshot(TypedDict):
    """Stable snapshot shape for one registered channel."""

    channel_id: str
    connected: bool


class HubSnapshot(TypedDict):
    """Stable compatibility snapshot shape for product callers."""

    elfie_id: str
    channels: List[ChannelSnapshot]
    pending_inbox: int
    outbox_count: int


@dataclass(frozen=True, slots=True)
class InboundDispositionInvariantError(RuntimeError):
    """A rejected compatibility result omitted its required typed error."""

    status: InboundDispositionStatus

    def __str__(self) -> str:
        return f"inbound disposition {self.status.value} omitted error"


class CommunicationHub:
    """Validate, dedupe, apply policy, then store or route envelopes."""

    def __init__(
        self,
        elfie_id: str,
        *,
        policy: Optional[CommunicationPolicy] = None,
        router: Optional[CommunicationRouter] = None,
    ) -> None:
        self.elfie_id = elfie_id
        self.policy = policy or CommunicationPolicy()
        self.router = router or CommunicationRouter()
        self.inbox = CommunicationInbox()
        self.outbox = CommunicationOutbox()
        self._inbound_dispositions: List[InboundDisposition] = []

    def bind_identity(self, elfie_id: str) -> None:
        self.elfie_id = elfie_id

    def register_channel(
        self,
        channel: RegisteredChannel,
        *,
        connect: bool = False,
        replace: bool = False,
    ) -> RegisteredChannel:
        registered = self.router.register(channel, replace=replace)
        if connect:
            registered.connect()
        return registered

    def receive_envelope(
        self,
        envelope: CommunicationEnvelope,
    ) -> InboundDisposition:
        """Admit one inbound envelope with observable replay disposition."""
        if envelope.direction is not MessageDirection.INBOUND:
            return self._record_disposition(
                envelope,
                InboundDispositionStatus.REJECTED,
                ErrorInfo(
                    code="invalid_direction",
                    message="入站边界只接受 inbound envelope",
                ),
            )
        if not self.inbox.claim_identity(envelope):
            return self._record_disposition(
                envelope,
                InboundDispositionStatus.DUPLICATE,
                ErrorInfo(
                    code="duplicate_message",
                    message="外部消息 identity 已处理",
                ),
            )
        if self.router.get(envelope.channel_id) is None:
            return self._record_disposition(
                envelope,
                InboundDispositionStatus.REJECTED,
                ErrorInfo(
                    code="unknown_channel",
                    message=f"通信通道未注册: {envelope.channel_id}",
                ),
            )
        try:
            self.policy.validate(envelope)
        except CommunicationPolicyError as exc:
            return self._record_disposition(
                envelope,
                InboundDispositionStatus.REJECTED,
                exc.error,
            )
        self.inbox.receive(envelope)
        return self._record_disposition(
            envelope,
            InboundDispositionStatus.ACCEPTED,
        )

    def send_envelope(self, envelope: CommunicationEnvelope) -> DeliveryReceipt:
        """Apply outbound policy and always return a typed delivery receipt."""
        if envelope.direction is not MessageDirection.OUTBOUND:
            receipt = DeliveryReceipt.for_envelope(
                envelope,
                status=DeliveryStatus.FAILED,
                error_code="invalid_direction",
                error_message="出站边界只接受 outbound envelope",
            )
        else:
            try:
                self.policy.validate(envelope)
            except CommunicationPolicyError as exc:
                receipt = DeliveryReceipt.for_envelope(
                    envelope,
                    status=DeliveryStatus.FAILED,
                    error_code=exc.error.code,
                    error_message=exc.error.message,
                    retryable=exc.error.retryable,
                )
            else:
                receipt = self.router.route(envelope)
        self.outbox.record(envelope, receipt)
        return receipt

    def send_batch(
        self,
        envelopes: Sequence[CommunicationEnvelope],
    ) -> Tuple[DeliveryReceipt, ...]:
        """Deliver one sequence in ordinal order with one receipt per envelope."""
        ordered = sorted(
            envelopes,
            key=lambda envelope: (
                envelope.sequence_id or "",
                envelope.ordinal if envelope.ordinal is not None else -1,
            ),
        )
        return tuple(self.send_envelope(envelope) for envelope in ordered)

    def receive(
        self,
        *,
        channel_id: str,
        sender_id: str,
        content: str,
        kind: MessageKind = MessageKind.TEXT,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> CommunicationEnvelope:
        """Compatibility adapter for the pre-envelope receive call shape."""
        message = CommunicationMessage(
            channel_id=channel_id,
            direction=MessageDirection.INBOUND,
            sender_id=sender_id,
            recipient_id=self.elfie_id,
            content=content,
            kind=kind,
            metadata=metadata or {},
        )
        envelope = message.to_envelope(elfie_id=self.elfie_id)
        disposition = self.receive_envelope(envelope)
        if disposition.status is InboundDispositionStatus.ACCEPTED:
            return envelope
        if disposition.error is None:
            raise InboundDispositionInvariantError(status=disposition.status)
        if disposition.error.code == "unknown_channel":
            raise KeyError(disposition.error.message)
        raise CommunicationPolicyError(error=disposition.error)

    def send(
        self,
        *,
        channel_id: str,
        recipient_id: str,
        content: str,
        kind: MessageKind = MessageKind.TEXT,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> DeliveryReceipt:
        """Compatibility adapter retaining policy exceptions until Task 14."""
        message = CommunicationMessage(
            channel_id=channel_id,
            direction=MessageDirection.OUTBOUND,
            sender_id=self.elfie_id,
            recipient_id=recipient_id,
            content=content,
            kind=kind,
            metadata=metadata or {},
        )
        envelope = message.to_envelope(elfie_id=self.elfie_id)
        self.policy.validate(envelope)
        return self.send_envelope(envelope)

    def drain_inbox(
        self,
        limit: Optional[int] = None,
    ) -> List[CommunicationEnvelope]:
        return self.inbox.drain(limit)

    @property
    def inbound_dispositions(self) -> Tuple[InboundDisposition, ...]:
        return tuple(self._inbound_dispositions)

    def snapshot(self) -> HubSnapshot:
        return {
            "elfie_id": self.elfie_id,
            "channels": [
                {
                    "channel_id": channel.channel_id,
                    "connected": channel.is_connected,
                }
                for channel in self.router.list_channels()
            ],
            "pending_inbox": self.inbox.pending_count,
            "outbox_count": len(self.outbox.history),
        }

    def _record_disposition(
        self,
        envelope: CommunicationEnvelope,
        status: InboundDispositionStatus,
        error: Optional[ErrorInfo] = None,
    ) -> InboundDisposition:
        disposition = InboundDisposition(
            message_id=envelope.message_id,
            channel_id=envelope.channel_id,
            status=status,
            error=error,
        )
        self._inbound_dispositions.append(disposition)
        return disposition


__all__ = (
    "ChannelSnapshot",
    "CommunicationHub",
    "HubSnapshot",
    "InboundDispositionInvariantError",
)
