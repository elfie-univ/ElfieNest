"""一只精灵独立拥有的类型化网络消息通信中心。"""

from __future__ import annotations

from threading import RLock
from typing import List, Optional, Sequence, Tuple

from elfie.brain.workspace.contracts import IngestReceipt
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
from elfie.communication.inbox import CommunicationInbox, InboxAdmitStatus
from elfie.communication.outbox import CommunicationOutbox
from elfie.communication.perception_adapter import (
    CommunicationPerceptionAdapter,
    DeliveryPerceptionCorrelation,
)
from elfie.communication.policy import CommunicationPolicy, CommunicationPolicyError
from elfie.communication.router import CommunicationRouter
from elfie.message_types import ErrorInfo


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
        self._max_dispositions = 1024
        self._evicted_dispositions = 0
        self._closed = False
        self._lock = RLock()

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
        with self._lock:
            return self._receive_envelope_locked(envelope)

    def _receive_envelope_locked(
        self,
        envelope: CommunicationEnvelope,
    ) -> InboundDisposition:
        if self._closed or self.inbox.closed:
            return self._record_disposition(
                envelope,
                InboundDispositionStatus.REJECTED,
                ErrorInfo(
                    code="communication_closed",
                    message="通信输入边界已关闭",
                ),
            )
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
        admit_status = self.inbox.admit(envelope)
        if admit_status is InboxAdmitStatus.CLOSED:
            return self._record_disposition(
                envelope,
                InboundDispositionStatus.REJECTED,
                ErrorInfo(
                    code="communication_closed",
                    message="通信输入边界已关闭",
                ),
            )
        if admit_status is InboxAdmitStatus.DUPLICATE:
            return self._record_disposition(
                envelope,
                InboundDispositionStatus.DUPLICATE,
                ErrorInfo(
                    code="duplicate_message",
                    message="外部消息 identity 已处理",
                ),
            )
        if admit_status is InboxAdmitStatus.FULL:
            return self._record_disposition(
                envelope,
                InboundDispositionStatus.REJECTED,
                ErrorInfo(
                    code="inbox_backpressure",
                    message="通信收件箱待处理消息已满",
                ),
            )
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
        with self._lock:
            return tuple(self._inbound_dispositions)

    @property
    def evicted_disposition_count(self) -> int:
        with self._lock:
            return self._evicted_dispositions

    def snapshot(self) -> HubSnapshot:
        return build_hub_snapshot(self.elfie_id, self.router, self.inbox, self.outbox)

    def close(self) -> None:
        """Close communication input and pending perception retries."""
        with self._lock:
            self._closed = True
            self.inbox.close()
            if self.perception_adapter is not None:
                self.perception_adapter.close()

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
        if len(self._inbound_dispositions) >= self._max_dispositions:
            self._inbound_dispositions.pop(0)
            self._evicted_dispositions += 1
        self._inbound_dispositions.append(disposition)
        return disposition


__all__ = (
    "CommunicationHub",
    "HubSnapshot",
)
