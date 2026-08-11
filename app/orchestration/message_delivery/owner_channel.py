"""Existing owner-reply channel at the application communication edge."""

from __future__ import annotations

import logging
from threading import Lock
from typing import Callable, Protocol

from pydantic import JsonValue

from app.features.communication import CommunicationError
from elfie.communication import CommunicationEnvelope, DeliveryReceipt, DeliveryStatus

from .errors import MessageDeliveryError
from .models import DeliverElfieReplyCommand
from .ports import OwnerMessageBroadcaster

logger = logging.getLogger("app.orchestration.message_delivery")


class ElfieReplyDelivery(Protocol):
    def deliver_elfie_reply(self, command: DeliverElfieReplyCommand) -> object: ...


class MessageDeliveryOwnerBroadcaster:
    """Map Nest owner events onto the canonical persisted realtime workflow."""

    def __init__(self, delivery: ElfieReplyDelivery) -> None:
        self._delivery = delivery

    def broadcast_to_owners(
        self,
        elfie_id: str,
        message_dict: dict[str, JsonValue],
    ) -> None:
        event = message_dict.get("event") or message_dict.get("action")
        payload = message_dict.get("payload") or {}
        if not isinstance(payload, dict):
            return
        text = self._message_text(str(event), payload)
        if not text:
            return
        emotion = str(payload.get("emotion") or "").strip()
        try:
            self._delivery.deliver_elfie_reply(
                DeliverElfieReplyCommand(
                    elfie_id=elfie_id,
                    text=text,
                    channel="web",
                    meta=f"情绪：{emotion}" if emotion else "实时回复",
                )
            )
        except (CommunicationError, MessageDeliveryError) as error:
            logger.warning("精灵聊天消息投递失败: %s", error)

    @staticmethod
    def _message_text(event: str, payload: dict[str, JsonValue]) -> str:
        if event == "speak_event":
            return str(payload.get("text") or "").strip()
        if event != "owner_message":
            return ""
        parts = payload.get("parts") or []
        if not isinstance(parts, list):
            return ""
        texts = [
            str(part.get("text") or "").strip()
            for part in parts
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return "\n".join(text for text in texts if text)


class GodotOwnerChannel:
    """Deliver outbound owner messages without entering the Body boundary."""

    channel_id = "godot-owner"

    def __init__(
        self,
        *,
        owner_broadcaster: Callable[[], OwnerMessageBroadcaster | None] | None = None,
    ) -> None:
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
        broadcaster = self._owner_broadcaster()
        if broadcaster is not None:
            broadcaster.broadcast_to_owners(
                str(envelope.meta.elfie_id),
                {
                    "action": "owner_message",
                    "payload": payload,
                },
            )
        return DeliveryReceipt.for_envelope(envelope, status=DeliveryStatus.SENT)


__all__ = (
    "GodotOwnerChannel",
    "MessageDeliveryOwnerBroadcaster",
    "OwnerMessageBroadcaster",
)
