"""CommunicationHub 类型化 envelope 集成测试。"""

from __future__ import annotations

from datetime import datetime, timezone

from elfie.communication import (
    CommunicationEnvelope,
    CommunicationHub,
    CommunicationPolicy,
    DeliveryReceipt,
    DeliveryStatus,
    ImagePart,
    InboundDispositionStatus,
    MessageDirection,
    TextPart,
)
from elfie.message_types import ActorRef, MediaRef, MessageMeta

NOW = datetime(2026, 7, 21, 4, 0, tzinfo=timezone.utc)


class EnvelopeSendFailure(RuntimeError):
    """Expected fake transport failure used by the router boundary test."""


class EnvelopeChannel:
    channel_id = "test"

    def __init__(self, *, fail: bool = False, raise_error: bool = False) -> None:
        self._connected = False
        self.fail = fail
        self.raise_error = raise_error
        self.sent: list[CommunicationEnvelope] = []

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def send_envelope(self, envelope: CommunicationEnvelope) -> DeliveryReceipt:
        self.sent.append(envelope)
        if self.raise_error:
            raise EnvelopeSendFailure
        status = DeliveryStatus.FAILED if self.fail else DeliveryStatus.SENT
        return DeliveryReceipt.for_envelope(
            envelope,
            status=status,
            error_code="adapter_send_failed" if self.fail else None,
        )


def inbound(
    *, event_id: str, dedupe_key: str, external_id: str
) -> CommunicationEnvelope:
    sender = ActorRef(actor_id="owner-1", source_kind="platform")
    return CommunicationEnvelope(
        meta=MessageMeta(
            event_id=event_id,
            elfie_id="elfie-1",
            source=sender,
            occurred_at=NOW,
            received_at=NOW,
            trace_id=f"trace-{event_id}",
        ),
        account_id="account-1",
        channel_id="test",
        conversation_id="conversation-1",
        sender=sender,
        recipients=(ActorRef(actor_id="elfie-1", source_kind="elfie"),),
        direction=MessageDirection.INBOUND,
        reply_to="external-parent-1",
        external_message_id=external_id,
        dedupe_key=dedupe_key,
        parts=(
            TextPart(text="你好"),
            ImagePart(
                media=MediaRef(
                    media_id="image-1",
                    uri="media://image-1",
                    mime_type="image/png",
                )
            ),
        ),
    )


def outbound(
    *, event_id: str, channel_id: str = "test", ordinal: int = 0
) -> CommunicationEnvelope:
    sender = ActorRef(actor_id="elfie-1", source_kind="elfie")
    return CommunicationEnvelope(
        meta=MessageMeta(
            event_id=event_id,
            elfie_id="elfie-1",
            source=sender,
            occurred_at=NOW,
            received_at=NOW,
            trace_id=f"trace-{event_id}",
        ),
        account_id="account-1",
        channel_id=channel_id,
        conversation_id="conversation-1",
        sender=sender,
        recipients=(ActorRef(actor_id="owner-1", source_kind="platform"),),
        direction=MessageDirection.OUTBOUND,
        dedupe_key=f"outbound-{event_id}",
        sequence_id="sequence-1",
        ordinal=ordinal,
        parts=(TextPart(text=f"消息 {ordinal}"),),
    )


def test_duplicate_external_identity_enters_inbox_once() -> None:
    hub = CommunicationHub("elfie-1")
    hub.register_channel(EnvelopeChannel())

    first = hub.receive_envelope(
        inbound(event_id="message-1", dedupe_key="webhook-1", external_id="external-1")
    )
    duplicate = hub.receive_envelope(
        inbound(event_id="message-2", dedupe_key="webhook-2", external_id="external-1")
    )

    assert first.status is InboundDispositionStatus.ACCEPTED
    assert duplicate.status is InboundDispositionStatus.DUPLICATE
    assert duplicate.error is not None
    assert duplicate.error.code == "duplicate_message"
    assert hub.inbox.pending_count == 1


def test_duplicate_dedupe_key_enters_inbox_once() -> None:
    hub = CommunicationHub("elfie-1")
    hub.register_channel(EnvelopeChannel())

    hub.receive_envelope(
        inbound(event_id="message-1", dedupe_key="webhook-1", external_id="external-1")
    )
    duplicate = hub.receive_envelope(
        inbound(event_id="message-2", dedupe_key="webhook-1", external_id="external-2")
    )

    assert duplicate.status is InboundDispositionStatus.DUPLICATE
    assert hub.inbox.pending_count == 1


def test_policy_denial_leaves_inbox_unchanged_and_is_typed() -> None:
    hub = CommunicationHub(
        "elfie-1",
        policy=CommunicationPolicy(allowed_channels=frozenset({"wechat"})),
    )
    hub.register_channel(EnvelopeChannel())

    disposition = hub.receive_envelope(
        inbound(
            event_id="message-denied", dedupe_key="denied-1", external_id="denied-1"
        )
    )

    assert disposition.status is InboundDispositionStatus.REJECTED
    assert disposition.error is not None
    assert disposition.error.code == "channel_not_allowed"
    assert hub.inbox.pending_count == 0


def test_outbound_policy_denial_returns_typed_failure_receipt() -> None:
    hub = CommunicationHub(
        "elfie-1",
        policy=CommunicationPolicy(allowed_channels=frozenset({"wechat"})),
    )

    receipt = hub.send_envelope(outbound(event_id="message-denied"))

    assert receipt.status is DeliveryStatus.FAILED
    assert receipt.error is not None
    assert receipt.error.code == "channel_not_allowed"


def test_unknown_channel_and_adapter_failure_return_typed_receipts() -> None:
    hub = CommunicationHub("elfie-1")

    unknown = hub.send_envelope(
        outbound(event_id="message-unknown", channel_id="missing")
    )
    hub.register_channel(EnvelopeChannel(fail=True), connect=True)
    failed = hub.send_envelope(outbound(event_id="message-failed"))

    assert unknown.status is DeliveryStatus.FAILED
    assert unknown.error is not None
    assert unknown.error.code == "unknown_channel"
    assert failed.status is DeliveryStatus.FAILED
    assert failed.error is not None
    assert failed.error.code == "adapter_send_failed"


def test_channel_exception_returns_typed_failure_receipt() -> None:
    hub = CommunicationHub("elfie-1")
    hub.register_channel(EnvelopeChannel(raise_error=True), connect=True)

    receipt = hub.send_envelope(outbound(event_id="message-error"))

    assert receipt.status is DeliveryStatus.FAILED
    assert receipt.error is not None
    assert receipt.error.code == "channel_send_failed"


def test_batch_delivery_orders_same_sequence_by_ordinal() -> None:
    hub = CommunicationHub("elfie-1")
    channel = EnvelopeChannel()
    hub.register_channel(channel, connect=True)
    envelopes = tuple(
        outbound(event_id=f"message-{ordinal}", ordinal=ordinal)
        for ordinal in (4, 1, 3, 0, 2)
    )

    receipts = hub.send_batch(envelopes)

    assert [message.ordinal for message in channel.sent] == [0, 1, 2, 3, 4]
    assert len(receipts) == 5
    assert all(receipt.status is DeliveryStatus.SENT for receipt in receipts)
    assert len({receipt.receipt_id for receipt in receipts}) == 5
