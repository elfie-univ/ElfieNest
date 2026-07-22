"""Godot owner-chat adapter at the application communication edge."""

from __future__ import annotations

from threading import Lock
from typing import Callable, Protocol

from pydantic import JsonValue

from elfie.communication import CommunicationEnvelope, DeliveryReceipt, DeliveryStatus
from nest.godot.api import GodotAPIServer


class OwnerMessageBroadcaster(Protocol):
    """Product owner WebSocket broadcast capability."""

    def broadcast_to_owners(
        self,
        elfie_id: str,
        message_dict: dict[str, JsonValue],
    ) -> None: ...


class GodotOwnerChannel:
    """Deliver outbound owner messages without entering the Body boundary."""

    channel_id = "godot-owner"

    def __init__(
        self,
        api_server: GodotAPIServer,
        *,
        owner_broadcaster: Callable[[], OwnerMessageBroadcaster | None] | None = None,
    ) -> None:
        self._api_server = api_server
        self._owner_broadcaster = owner_broadcaster or (lambda: None)
        self._connected = False
        self._lock = Lock()

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._connected

    def connect(self) -> bool:
        with self._lock:
            self._connected = True
        return True

    def disconnect(self) -> None:
        with self._lock:
            self._connected = False

    def send_envelope(self, envelope: CommunicationEnvelope) -> DeliveryReceipt:
        payload: dict[str, JsonValue] = {
            "elfie_id": str(envelope.meta.elfie_id),
            "conversation_id": envelope.conversation_id,
            "message_id": str(envelope.meta.event_id),
            "parts": [part.model_dump(mode="json") for part in envelope.parts],
        }
        self._api_server.send_action("owner_message", payload)
        broadcaster = self._owner_broadcaster()
        if broadcaster is not None:
            broadcaster.broadcast_to_owners(str(envelope.meta.elfie_id), {
                "action": "owner_message",
                "payload": payload,
            })
        return DeliveryReceipt.for_envelope(envelope, status=DeliveryStatus.SENT)


__all__ = ("GodotOwnerChannel", "OwnerMessageBroadcaster")
