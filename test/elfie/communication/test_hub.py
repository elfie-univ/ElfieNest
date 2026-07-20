import pytest

from elfie import ElfieFactory
from elfie.communication import (
    CommunicationHub,
    CommunicationMessage,
    CommunicationPolicy,
    CommunicationPolicyError,
    DeliveryStatus,
    MessageDirection,
)


class FakeChannel:
    def __init__(self, channel_id: str = "test", succeeds: bool = True) -> None:
        self.channel_id = channel_id
        self.succeeds = succeeds
        self._connected = False
        self.sent = []

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def send(self, message: CommunicationMessage) -> bool:
        self.sent.append(message)
        return self.succeeds


def test_hub_routes_outbound_message_and_records_receipt() -> None:
    hub = CommunicationHub("elfie-1")
    channel = FakeChannel()
    hub.register_channel(channel, connect=True)

    receipt = hub.send(
        channel_id="test",
        recipient_id="owner-1",
        content="你好",
    )

    assert receipt.status is DeliveryStatus.SENT
    assert channel.sent[0].sender_id == "elfie-1"
    assert channel.sent[0].direction is MessageDirection.OUTBOUND
    assert hub.outbox.get(receipt.message_id).receipt is receipt


def test_hub_receives_messages_without_using_body_sensor_queue() -> None:
    hub = CommunicationHub("elfie-1")
    hub.register_channel(FakeChannel())

    received = hub.receive(
        channel_id="test",
        sender_id="owner-1",
        content="今天好吗？",
    )

    assert received.recipient_id == "elfie-1"
    assert hub.inbox.pending_count == 1
    assert hub.drain_inbox() == [received]
    assert hub.inbox.pending_count == 0


def test_hub_records_failed_channel_delivery() -> None:
    hub = CommunicationHub("elfie-1")
    hub.register_channel(FakeChannel(succeeds=False), connect=True)

    receipt = hub.send(channel_id="test", recipient_id="owner", content="消息")

    assert receipt.status is DeliveryStatus.FAILED
    assert "未确认" in receipt.error
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

    with pytest.raises(CommunicationPolicyError, match="不允许"):
        hub.send(channel_id="test", recipient_id="owner", content="你好")


def test_canonical_elfie_owns_hub_and_updates_its_identity() -> None:
    elfie = ElfieFactory().create(elfie_id="before", memory_db_path=":memory:")
    elfie.communication.register_channel(FakeChannel(), connect=True)

    elfie.bind_identity("after")
    receipt = elfie.send_message(
        channel_id="test", recipient_id="owner", content="你好"
    )

    assert receipt.delivered is True
    assert elfie.communication.elfie_id == "after"
    assert elfie.describe()["communication"]["outbox_count"] == 1


def test_factory_rebinds_injected_hub_to_profile_identity() -> None:
    hub = CommunicationHub("stale-id")

    elfie = ElfieFactory().create(
        elfie_id="current-id",
        memory_db_path=":memory:",
        communication=hub,
    )

    assert elfie.communication is hub
    assert hub.elfie_id == "current-id"
