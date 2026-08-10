"""Consumer-owned persistence boundary for product Communication."""

from __future__ import annotations

from typing import Optional, Protocol, Tuple

from .port_models import ConversationMessageWrite, StoredConversationMessage


class CommunicationPortError(RuntimeError):
    """The authoritative conversation store could not complete an operation."""


class ConversationHistoryPort(Protocol):
    def list_messages(
        self,
        elfie_id: str,
        *,
        conversation_id: str,
        user_id: int,
    ) -> Tuple[StoredConversationMessage, ...]: ...

    def append_message(
        self, message: ConversationMessageWrite
    ) -> StoredConversationMessage: ...

    def owner_user_id(self, elfie_id: str) -> Optional[int]: ...


__all__ = ("CommunicationPortError", "ConversationHistoryPort")
