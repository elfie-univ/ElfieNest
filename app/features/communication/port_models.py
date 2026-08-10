"""Technical records exchanged with Communication-owned Ports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import MessageSender


@dataclass(frozen=True)
class StoredConversationMessage:
    id: int
    sender: MessageSender
    text: str
    created_at: str


@dataclass(frozen=True)
class ConversationMessageWrite:
    elfie_id: str
    conversation_id: str
    sender: MessageSender
    text: str
    channel: str
    user_id: int
    message_id: Optional[str] = None
    meta: str = ""


__all__ = ("ConversationMessageWrite", "StoredConversationMessage")
