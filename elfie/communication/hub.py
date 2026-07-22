"""一只精灵独立拥有的类型化网络消息通信中心。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from elfie.brain.perception_types import IngestReceipt
from elfie.communication.channel import CommunicationChannel
from elfie.communication.contracts import (
    CommunicationEnvelope,
    DeliveryReceipt,
    DeliveryStatus,
    InboundDisposition,
    InboundDispositionStatus,
    MessageDirection,
)
from elfie.communication.hub_snapshot import (
    HubSnapshot,
    build_hub_snapshot,
)
from elfie.communication.inbox import CommunicationInbox
from elfie.communication.outbox import CommunicationOutbox
from elfie.communication.perception_adapter import (
    CommunicationPerceptionAdapter,
    DeliveryPerceptionCorrelation,
)
from elfie.communication.policy import CommunicationPolicy, CommunicationPolicyError
from elfie.communication.router import CommunicationRouter
from elfie.message_types import ErrorInfo


@dataclass(frozen=True)  # noqa: SLOTS_OK - Python 3.9
class InboundDispositionInvariantError(RuntimeError):
    """A rejected inbound result omitted its required typed error."""

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
        perception_adapter: Optional[CommunicationPerceptionAdapter] = None,
    ) -> None:
        self.elfie_id = elfie_id
        self.policy = policy or CommunicationPolicy()
        self.router = router or CommunicationRouter()
        self.inbox = CommunicationInbox()
        self.outbox = CommunicationOutbox()
        self.perception_adapter = perception_adapter
        self._inbound_dispositions: List[InboundDisposition] = []

    def bind_identity(self, elfie_id: str) -> None:
        self.elfie_id = elfie_id

    def bind_perception_adapter(
        self,
        adapter: CommunicationPerceptionAdapter,
    ) -> None:
        """Bind the Brain-facing producer after the Elfie workspace exists."""
        self.perception_adapter = adapter

    def register_channel(
        self,
        channel: CommunicationChannel,
        *,
        connect: bool = False,
        replace: bool = False,
    ) -> CommunicationChannel:
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
        if not self.inbox.claim_identity(envelope):
            return self._record_disposition(
                envelope,
                InboundDispositionStatus.DUPLICATE,
                ErrorInfo(
                    code="duplicate_message",
                    message="外部消息 identity 已处理",
                ),
            )
        self.inbox.receive(envelope)
        if self.perception_adapter is not None:
            attempt = self.perception_adapter.publish_inbound(envelope)
            if attempt.completed:
                self.inbox.mark_cognitive_delivery(envelope)
        return self._record_disposition(
            envelope,
            InboundDispositionStatus.ACCEPTED,
        )

    def send_envelope(
        self,
        envelope: CommunicationEnvelope,
        *,
        correlation: Optional[DeliveryPerceptionCorrelation] = None,
    ) -> DeliveryReceipt:
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
        if self.perception_adapter is not None and correlation is not None:
            self.perception_adapter.publish_delivery(envelope, receipt, correlation)
        return receipt

    def retry_perception(self) -> Tuple[IngestReceipt, ...]:
        """Retry backpressured communication facts once in source order."""
        if self.perception_adapter is None:
            return ()
        attempts = self.perception_adapter.retry_inbound()
        for attempt in attempts:
            if attempt.completed:
                self.inbox.mark_cognitive_delivery(attempt.envelope)
        return tuple(attempt.receipt for attempt in attempts) + (
            self.perception_adapter.retry_delivery()
        )

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

    def drain_inbox(
        self,
        limit: Optional[int] = None,
    ) -> List[CommunicationEnvelope]:
        return self.inbox.drain(limit)

    @property
    def inbound_dispositions(self) -> Tuple[InboundDisposition, ...]:
        return tuple(self._inbound_dispositions)

    def snapshot(self) -> HubSnapshot:
        return build_hub_snapshot(self.elfie_id, self.router, self.inbox, self.outbox)

    def _record_disposition(
        self,
        envelope: CommunicationEnvelope,
        status: InboundDispositionStatus,
        error: Optional[ErrorInfo] = None,
    ) -> InboundDisposition:
        disposition = InboundDisposition(
            message_id=envelope.meta.event_id,
            channel_id=envelope.channel_id,
            status=status,
            error=error,
        )
        self._inbound_dispositions.append(disposition)
        return disposition


__all__ = (
    "CommunicationHub",
    "HubSnapshot",
    "InboundDispositionInvariantError",
)
