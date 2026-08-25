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
    """Product owner delivery capability consumed by the communication channel.

    ``True`` means the authoritative history accepted the reply.  The realtime
    publisher may still be pending and can be retried with the same message ID.
    """

    def broadcast_to_owners(
        self,
        elfie_id: str,
        message_dict: dict[str, JsonValue],
    ) -> bool: ...


__all__ = (
    "ElfieMessageDeliveryPort",
    "LiveConversationPort",
    "MessageDeliveryPortError",
    "OwnerMessageBroadcaster",
)
