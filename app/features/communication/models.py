"""Commands, queries and results owned by product Communication."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Tuple

MessageSender = Literal["user", "elfie", "system"]


@dataclass(frozen=True)
class ListConversationsQuery:
    pass


@dataclass(frozen=True)
class GetConversationQuery:
    elfie_id: str


@dataclass(frozen=True)
class ListMessagesQuery:
    elfie_id: str


@dataclass(frozen=True)
class RecordUserMessageCommand:
    elfie_id: str
    text: str
    channel: str
    message_id: Optional[str] = None
    conversation_id: Optional[str] = None
    external_actor_id: Optional[str] = None
    external_actor_display_name: Optional[str] = None


@dataclass(frozen=True)
class RecordElfieMessageCommand:
    elfie_id: str
    text: str
    channel: str
    meta: str
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None


@dataclass(frozen=True)
class ConversationAccessResult:
    elfie_id: str
    owner_user_id: int
    owner_account_id: str


@dataclass(frozen=True)
class PreparedUserMessageResult:
    access: ConversationAccessResult
    text: str
    channel: str
    message_id: Optional[str]
    conversation_id: Optional[str] = None
    external_actor_id: Optional[str] = None
    external_actor_display_name: Optional[str] = None


@dataclass(frozen=True)
class MessageResult:
    id: int
    elfie_id: str
    sender: MessageSender
    text: str
    created_at: str


@dataclass(frozen=True)
class MessagesResult:
    items: Tuple[MessageResult, ...]


@dataclass(frozen=True)
class ConversationResult:
    elfie_id: str
    name: str
    portrait_url: str
    last_message_preview: str
    last_message_at: Optional[str]


@dataclass(frozen=True)
class ConversationsResult:
    items: Tuple[ConversationResult, ...]


@dataclass(frozen=True)
class RecordedElfieMessageResult:
    owner_user_id: int
    message: MessageResult
    realtime_delivered: bool = True


__all__ = (
    "ConversationAccessResult",
    "ConversationResult",
    "ConversationsResult",
    "GetConversationQuery",
    "ListConversationsQuery",
    "ListMessagesQuery",
    "MessageResult",
    "MessageSender",
    "MessagesResult",
    "PreparedUserMessageResult",
    "RecordElfieMessageCommand",
    "RecordedElfieMessageResult",
    "RecordUserMessageCommand",
)
