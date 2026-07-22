from datetime import datetime, timezone

from elfie.communication import (
    CommunicationEnvelope,
    DeliveryStatus,
    MessageDirection,
    TelegramChannel,
    TelegramConnector,
    TextPart,
    WeChatChannel,
    WeChatConnector,
)
from elfie.message_types import ActorRef, MessageMeta

NOW = datetime(2026, 7, 22, 0, 0, tzinfo=timezone.utc)


def outbound(channel_id: str, recipient_id: str) -> CommunicationEnvelope:
    sender = ActorRef(actor_id="elfie-1", source_kind="elfie")
    return CommunicationEnvelope(
        meta=MessageMeta(
            event_id=f"message-{channel_id}",
            elfie_id="elfie-1",
            source=sender,
            occurred_at=NOW,
            received_at=NOW,
            trace_id=f"trace-{channel_id}",
        ),
        account_id=f"account-{channel_id}",
        channel_id=channel_id,
        conversation_id=recipient_id,
        sender=sender,
        recipients=(ActorRef(actor_id=recipient_id, source_kind="platform"),),
        direction=MessageDirection.OUTBOUND,
        dedupe_key=f"dedupe-{channel_id}",
        parts=(TextPart(text="你好"),),
    )


def test_wechat_channel_sends_envelope_with_typed_receipt() -> None:
    connector = WeChatConnector()
    channel = WeChatChannel(connector)

    assert channel.connect() is True
    receipt = channel.send_envelope(outbound("wechat", "owner"))

    assert receipt.status is DeliveryStatus.SENT
    assert receipt.channel_id == "wechat"
    channel.disconnect()
    assert connector.is_connected is False


def test_telegram_channel_sends_envelope_with_typed_receipt() -> None:
    connector = TelegramConnector()
    channel = TelegramChannel(connector)

    assert channel.connect() is True
    receipt = channel.send_envelope(outbound("telegram", "chat-1"))

    assert receipt.status is DeliveryStatus.SENT
    assert receipt.channel_id == "telegram"
    channel.disconnect()
    assert connector.is_connected is False
