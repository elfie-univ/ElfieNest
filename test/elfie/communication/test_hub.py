from __future__ import annotations

from datetime import datetime, timezone

from elfie import ElfieFactory
from elfie.communication import (
    CommunicationEnvelope,
    CommunicationHub,
    CommunicationPolicy,
    DeliveryReceipt,
    DeliveryStatus,
    InboundDispositionStatus,
    MessageDirection,
    TextPart,
)
from elfie.communication.outbox import CommunicationOutbox
from elfie.message_types import ActorRef, MessageMeta

NOW = datetime(2026, 7, 22, 0, 0, tzinfo=timezone.utc)


class FakeChannel:
    def __init__(self, channel_id: str = "test", succeeds: bool = True) -> None:
        self.channel_id = channel_id
        self.succeeds = succeeds
        self._connected = False
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
        return DeliveryReceipt.for_envelope(
            envelope,
            status=DeliveryStatus.SENT if self.succeeds else DeliveryStatus.FAILED,
            error_code=None if self.succeeds else "send_not_confirmed",
            error_message=None if self.succeeds else "通信通道未确认发送成功",
            retryable=not self.succeeds,
        )


def test_hub_routes_outbound_message_and_records_receipt() -> None:
    hub = CommunicationHub("elfie-1")
    channel = FakeChannel()
    hub.register_channel(channel, connect=True)

    envelope = _envelope(MessageDirection.OUTBOUND, "elfie-1", "owner-1", "你好")
    receipt = hub.send_envelope(envelope)

    assert receipt.status is DeliveryStatus.SENT
    assert channel.sent[0].sender.actor_id == "elfie-1"
    assert channel.sent[0].direction is MessageDirection.OUTBOUND
    assert hub.outbox.get(receipt.message_id).receipt is receipt


def test_outbox_retains_only_bounded_recent_history() -> None:
    outbox = CommunicationOutbox(history_capacity=1)
    first = _envelope(MessageDirection.OUTBOUND, "elfie-1", "owner-1", "一")
    second = _envelope(
        MessageDirection.OUTBOUND,
        "elfie-1",
        "owner-1",
        "二",
        event_id="message-2",
    )

    outbox.record(
        first,
        DeliveryReceipt.for_envelope(first, status=DeliveryStatus.SENT),
    )
    outbox.record(
        second,
        DeliveryReceipt.for_envelope(second, status=DeliveryStatus.SENT),
    )

    assert outbox.get(str(first.meta.event_id)) is None
    assert outbox.history[0].message is second
    assert outbox.evicted_count == 1


def test_hub_receives_messages_without_using_body_sensor_queue() -> None:
    hub = CommunicationHub("elfie-1")
    hub.register_channel(FakeChannel())

    received = _envelope(MessageDirection.INBOUND, "owner-1", "elfie-1", "今天好吗？")
    hub.receive_envelope(received)

    assert received.recipients[0].actor_id == "elfie-1"
    assert hub.inbox.pending_count == 1
    assert hub.drain_inbox() == [received]
    assert hub.inbox.pending_count == 0


def test_rejected_message_does_not_claim_replay_identity() -> None:
    # Given: the first delivery reaches an unregistered channel.
    hub = CommunicationHub("elfie-1")
    envelope = _envelope(
        MessageDirection.INBOUND,
        "owner-1",
        "elfie-1",
        "retry me",
    )
    rejected = hub.receive_envelope(envelope)
    assert rejected.status is InboundDispositionStatus.REJECTED
    hub.register_channel(FakeChannel(), connect=True)

    # When: the same transport delivery is retried after the channel becomes valid.
    retried = hub.receive_envelope(envelope)

    # Then: a policy rejection did not permanently consume its dedupe identity.
    assert retried.status is InboundDispositionStatus.ACCEPTED


def test_hub_without_perception_sink_preserves_manual_inbox_delivery() -> None:
    # Given: the Hub has no cognitive perception sink.
    hub = CommunicationHub("elfie-1")
    hub.register_channel(FakeChannel())

    # When: one inbound platform message is admitted.
    received = _envelope(
        MessageDirection.INBOUND,
        "owner-1",
        "elfie-1",
        "仍由调用方手动读取",
    )
    hub.receive_envelope(received)

    # Then: the envelope remains pending until the caller drains it.
    assert hub.inbox.pending_count == 1
    assert hub.drain_inbox() == [received]


def test_hub_records_failed_channel_delivery() -> None:
    hub = CommunicationHub("elfie-1")
    hub.register_channel(FakeChannel(succeeds=False), connect=True)

    receipt = hub.send_envelope(
        _envelope(MessageDirection.OUTBOUND, "elfie-1", "owner", "消息")
    )

    assert receipt.status is DeliveryStatus.FAILED
    assert receipt.error is not None
    assert "未确认" in receipt.error.message
    assert hub.outbox.get(receipt.message_id).receipt is receipt


def test_policy_rejects_disallowed_channels_and_long_messages() -> None:
    hub = CommunicationHub(
        "elfie-1",
        policy=CommunicationPolicy(
            allowed_channels=frozenset({"wechat"}),
            max_content_length=4,
        ),
    )
    hub.register_channel(FakeChannel(channel_id="test"), connect=True)

    receipt = hub.send_envelope(
        _envelope(MessageDirection.OUTBOUND, "elfie-1", "owner", "你好")
    )

    assert receipt.status is DeliveryStatus.FAILED
    assert receipt.error is not None
    assert "不允许" in receipt.error.message


def test_canonical_elfie_owns_hub_and_updates_its_identity() -> None:
    elfie = ElfieFactory().create(elfie_id="before", memory_db_path=":memory:")
    elfie.communication.register_channel(FakeChannel(), connect=True)

    elfie.bind_identity("after")
    receipt = elfie.communication.send_envelope(
        _envelope(MessageDirection.OUTBOUND, "after", "owner", "你好")
    )

    assert receipt.status is DeliveryStatus.SENT
    assert elfie.communication.elfie_id == "after"
    assert elfie.communication.snapshot()["outbox_count"] == 1


def test_factory_rebinds_injected_hub_to_profile_identity() -> None:
    hub = CommunicationHub("stale-id")

    elfie = ElfieFactory().create(
        elfie_id="current-id",
        memory_db_path=":memory:",
        communication=hub,
    )

    assert elfie.communication is hub
    assert hub.elfie_id == "current-id"


def _envelope(
    direction: MessageDirection,
    sender_id: str,
    recipient_id: str,
    content: str,
    *,
    event_id: str | None = None,
) -> CommunicationEnvelope:
    sender = ActorRef(
        actor_id=sender_id,
        source_kind="platform" if direction is MessageDirection.INBOUND else "elfie",
    )
    return CommunicationEnvelope(
        meta=MessageMeta(
            event_id=event_id or f"message-{sender_id}-{recipient_id}",
            elfie_id=(
                recipient_id if direction is MessageDirection.INBOUND else sender_id
            ),
            source=sender,
            occurred_at=NOW,
            received_at=NOW,
            trace_id=f"trace-{sender_id}-{recipient_id}",
        ),
        account_id="account-test",
        channel_id="test",
        conversation_id=recipient_id,
        sender=sender,
        recipients=(
            ActorRef(
                actor_id=recipient_id,
                source_kind=(
                    "elfie" if direction is MessageDirection.INBOUND else "platform"
                ),
            ),
        ),
        direction=direction,
        dedupe_key=f"dedupe-{sender_id}-{recipient_id}-{content}",
        parts=(TextPart(text=content),),
    )
