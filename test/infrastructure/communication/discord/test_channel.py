from datetime import datetime, timezone

from elfie.communication import (
    CommunicationEnvelope,
    DeliveryStatus,
    MessageDirection,
    TextPart,
)
from elfie.message_types import ActorRef, MessageMeta
from infrastructure.communication import DiscordChannel, DiscordConnector
from infrastructure.communication.discord.client import DiscordSentMessage


def test_discord_channel_sends_only_authorized_text_conversation() -> None:
    class Client:
        def __init__(self) -> None:
            self.sent: list[tuple[str, str]] = []
            self.closed = False

        def send_message(self, channel_id: str, text: str) -> DiscordSentMessage:
            self.sent.append((channel_id, text))
            return DiscordSentMessage("17")

        def close(self) -> None:
            self.closed = True

    sender = ActorRef(actor_id="elfie-1", source_kind="elfie")
    envelope = CommunicationEnvelope(
        meta=MessageMeta(
            event_id="message-discord",
            elfie_id="elfie-1",
            source=sender,
            occurred_at=datetime.now(timezone.utc),
            received_at=datetime.now(timezone.utc),
            trace_id="trace-discord",
        ),
        account_id="account-discord",
        channel_id="discord",
        conversation_id="discord:1701",
        sender=sender,
        recipients=(ActorRef(actor_id="discord:1701", source_kind="platform"),),
        direction=MessageDirection.OUTBOUND,
        dedupe_key="dedupe-discord",
        parts=(TextPart(text="你好"),),
    )
    client = Client()
    channel = DiscordChannel(
        DiscordConnector(client),
        elfie_id="elfie-1",
        bot_id="991",
        conversation_id="discord:1701",
    )
    channel.connect()

    receipt = channel.send_envelope(envelope)
    assert receipt.status is DeliveryStatus.SENT
    assert client.sent == [("1701", "你好")]
    channel.disconnect()
    assert client.closed is True
