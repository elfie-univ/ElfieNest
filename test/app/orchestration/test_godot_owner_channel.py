"""Godot owner-channel contract tests."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import JsonValue

from app.orchestration.godot_owner_channel import GodotOwnerChannel
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
    ) -> None:
        self.messages.append((elfie_id, message_dict))


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
