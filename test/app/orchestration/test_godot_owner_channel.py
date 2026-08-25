"""Godot owner-channel contract tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from pydantic import JsonValue

from app.features.communication import (
    CommunicationUnavailable,
    MessageResult,
    RecordedElfieMessageResult,
)
from app.orchestration.message_delivery import (
    DeliverElfieReplyCommand,
    GodotOwnerChannel,
    MessageDeliveryFacade,
    MessageDeliveryOwnerBroadcaster,
)
from elfie.communication import (
    CommunicationEnvelope,
    DeliveryStatus,
    MessageDirection,
    TextPart,
)
from elfie.message_types import ActorRef, MessageMeta

NOW = datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc)


class RecordingBroadcaster:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict[str, JsonValue]]] = []

    def broadcast_to_owners(
        self,
        elfie_id: str,
        message_dict: dict[str, JsonValue],
    ) -> bool:
        self.messages.append((elfie_id, message_dict))
        return True


def test_outbound_owner_message_uses_envelope_event_identity() -> None:
    # Given: the canonical envelope stores identity only under MessageMeta.
    broadcaster = RecordingBroadcaster()
    channel = GodotOwnerChannel(owner_broadcaster=lambda: broadcaster)
    sender = ActorRef(actor_id="elfie-1", source_kind="elfie")
    envelope = CommunicationEnvelope(
        meta=MessageMeta(
            event_id="message-owner-1",
            elfie_id="elfie-1",
            source=sender,
            occurred_at=NOW,
            received_at=NOW,
            trace_id="trace-owner-1",
        ),
        account_id="owner-account",
        channel_id="godot-owner",
        conversation_id="owner-chat",
        sender=sender,
        recipients=(ActorRef(actor_id="owner-1", source_kind="owner"),),
        direction=MessageDirection.OUTBOUND,
        dedupe_key="dedupe-owner-1",
        parts=(TextPart(text="你好"),),
    )

    # When: the app adapter sends the typed envelope to the owner transport.
    receipt = channel.send_envelope(envelope)

    # Then: the owner message and receipt retain the canonical event ID.
    assert broadcaster.messages[0] == (
        "elfie-1",
        {
            "action": "owner_message",
            "payload": {
                "elfie_id": "elfie-1",
                "conversation_id": "owner-chat",
                "message_id": "message-owner-1",
                "parts": [
                    {
                        "type": "text",
                        "text": "你好",
                    }
                ],
            },
        },
    )
    assert receipt.message_id == envelope.meta.event_id
    assert receipt.status is DeliveryStatus.SENT


def test_nest_owner_message_uses_canonical_reply_delivery() -> None:
    delivery = MagicMock(spec=MessageDeliveryFacade)
    broadcaster = MessageDeliveryOwnerBroadcaster(delivery)

    assert (
        broadcaster.broadcast_to_owners(
            "elfie-1",
            {
                "action": "owner_message",
                "payload": {
                    "parts": [
                        {"type": "text", "text": "你好"},
                        {"type": "text", "text": "主人"},
                    ],
                    "emotion": "happy",
                    "conversation_id": "owner-chat",
                    "message_id": "outbound-owner-1",
                },
            },
        )
        is True
    )

    delivery.deliver_elfie_reply.assert_called_once_with(
        DeliverElfieReplyCommand(
            elfie_id="elfie-1",
            text="你好\n主人",
            channel="web",
            meta="情绪：happy",
            conversation_id="owner-chat",
            message_id="outbound-owner-1",
        )
    )


def test_nest_speech_event_uses_canonical_reply_delivery() -> None:
    delivery = MagicMock(spec=MessageDeliveryFacade)
    broadcaster = MessageDeliveryOwnerBroadcaster(delivery)

    assert (
        broadcaster.broadcast_to_owners(
            "elfie-1",
            {"action": "speak_event", "payload": {"text": "在这里"}},
        )
        is True
    )

    delivery.deliver_elfie_reply.assert_called_once_with(
        DeliverElfieReplyCommand(
            elfie_id="elfie-1",
            text="在这里",
            channel="web",
            meta="实时回复",
        )
    )


def test_owner_broadcaster_returns_false_when_history_or_realtime_fails() -> None:
    delivery = MagicMock(spec=MessageDeliveryFacade)
    delivery.deliver_elfie_reply.side_effect = CommunicationUnavailable("offline")
    broadcaster = MessageDeliveryOwnerBroadcaster(delivery)

    accepted = broadcaster.broadcast_to_owners(
        "elfie-1",
        {
            "action": "owner_message",
            "payload": {"parts": [{"type": "text", "text": "你好"}]},
        },
    )

    assert accepted is False


def test_owner_broadcaster_keeps_history_success_when_realtime_is_unavailable() -> None:
    delivery = MagicMock(spec=MessageDeliveryFacade)
    delivery.deliver_elfie_reply.return_value = RecordedElfieMessageResult(
        owner_user_id=7,
        message=MessageResult(
            id=1,
            elfie_id="elfie-1",
            sender="elfie",
            text="你好",
            created_at="2026-07-22T08:00:00.000Z",
        ),
        realtime_delivered=False,
    )
    broadcaster = MessageDeliveryOwnerBroadcaster(delivery)

    assert (
        broadcaster.broadcast_to_owners(
            "elfie-1",
            {
                "action": "owner_message",
                "payload": {"parts": [{"type": "text", "text": "你好"}]},
            },
        )
        is True
    )


def test_owner_channel_reports_failed_when_broadcaster_is_unavailable() -> None:
    channel = GodotOwnerChannel()
    sender = ActorRef(actor_id="elfie-1", source_kind="elfie")
    envelope = CommunicationEnvelope(
        meta=MessageMeta(
            event_id="message-owner-missing",
            elfie_id="elfie-1",
            source=sender,
            occurred_at=NOW,
            received_at=NOW,
            trace_id="trace-owner-missing",
        ),
        account_id="owner-account",
        channel_id="godot-owner",
        conversation_id="owner-chat",
        sender=sender,
        recipients=(ActorRef(actor_id="owner-1", source_kind="owner"),),
        direction=MessageDirection.OUTBOUND,
        dedupe_key="dedupe-owner-missing",
        parts=(TextPart(text="你好"),),
    )

    receipt = channel.send_envelope(envelope)

    assert receipt.status is DeliveryStatus.FAILED
    assert receipt.error is not None
    assert receipt.error.code == "owner_broadcaster_unavailable"


def test_owner_channel_does_not_claim_sent_when_broadcaster_rejects() -> None:
    class RejectingBroadcaster:
        def broadcast_to_owners(
            self,
            elfie_id: str,
            message_dict: dict[str, JsonValue],
        ) -> bool:
            del elfie_id, message_dict
            return False

    broadcaster = RejectingBroadcaster()
    channel = GodotOwnerChannel(owner_broadcaster=lambda: broadcaster)
    sender = ActorRef(actor_id="elfie-1", source_kind="elfie")
    envelope = CommunicationEnvelope(
        meta=MessageMeta(
            event_id="message-owner-rejected",
            elfie_id="elfie-1",
            source=sender,
            occurred_at=NOW,
            received_at=NOW,
            trace_id="trace-owner-rejected",
        ),
        account_id="owner-account",
        channel_id="godot-owner",
        conversation_id="owner-chat",
        sender=sender,
        recipients=(ActorRef(actor_id="owner-1", source_kind="owner"),),
        direction=MessageDirection.OUTBOUND,
        dedupe_key="dedupe-owner-rejected",
        parts=(TextPart(text="你好"),),
    )

    receipt = channel.send_envelope(envelope)

    assert receipt.status is DeliveryStatus.FAILED
    assert receipt.error is not None
    assert receipt.error.code == "owner_delivery_unconfirmed"
