"""Consumer-owned technical boundaries for message delivery."""

from __future__ import annotations

from typing import Protocol

from pydantic import JsonValue

from .port_models import (
    DeliveryAdmission,
    LiveConversationMessage,
    UserMessageDeliveryAttempt,
)


class MessageDeliveryPortError(RuntimeError):
    """A delivery or realtime transport boundary failed."""


class ElfieMessageDeliveryPort(Protocol):
    def deliver_user_message(
        self, attempt: UserMessageDeliveryAttempt
    ) -> DeliveryAdmission: ...


class LiveConversationPort(Protocol):
    def publish_message(self, message: LiveConversationMessage) -> None: ...


class OwnerMessageBroadcaster(Protocol):
    """Product owner WebSocket broadcast capability consumed by delivery."""

    def broadcast_to_owners(
        self,
        elfie_id: str,
        message_dict: dict[str, JsonValue],
    ) -> None: ...


__all__ = (
    "ElfieMessageDeliveryPort",
    "LiveConversationPort",
    "MessageDeliveryPortError",
    "OwnerMessageBroadcaster",
)
