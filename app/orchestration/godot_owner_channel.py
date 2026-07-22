"""Godot owner-chat adapter at the application communication edge."""

from __future__ import annotations

from threading import Lock

from elfie.communication import CommunicationEnvelope, DeliveryReceipt, DeliveryStatus
from nest.godot.api import GodotAPIServer


class GodotOwnerChannel:
    """Deliver outbound owner messages without entering the Body boundary."""

    channel_id = "godot-owner"

    def __init__(self, api_server: GodotAPIServer) -> None:
        self._api_server = api_server
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
        self._api_server.send_action(
            "owner_message",
            {
                "elfie_id": str(envelope.meta.elfie_id),
                "conversation_id": envelope.conversation_id,
                "message_id": str(envelope.meta.event_id),
                "parts": tuple(
                    part.model_dump(mode="json") for part in envelope.parts
                ),
            },
        )
        return DeliveryReceipt.for_envelope(envelope, status=DeliveryStatus.SENT)


__all__ = ("GodotOwnerChannel",)
