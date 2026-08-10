"""Public facade for product conversations and user-visible message history."""

from .errors import (
    CommunicationError,
    CommunicationUnavailable,
    ConversationNotFound,
    MessageInvalid,
)
from .models import (
    ConversationAccessResult,
    ConversationResult,
    ConversationsResult,
    GetConversationQuery,
    ListConversationsQuery,
    ListMessagesQuery,
    MessageResult,
    MessageSender,
    MessagesResult,
    PreparedUserMessageResult,
    RecordedElfieMessageResult,
    RecordElfieMessageCommand,
    RecordUserMessageCommand,
)
from .port_models import ConversationMessageWrite, StoredConversationMessage
from .ports import CommunicationPortError, ConversationHistoryPort
from .service import CommunicationFacade

__all__ = (
    "CommunicationError",
    "CommunicationFacade",
    "CommunicationPortError",
    "CommunicationUnavailable",
    "ConversationAccessResult",
    "ConversationHistoryPort",
    "ConversationMessageWrite",
    "ConversationNotFound",
    "ConversationResult",
    "ConversationsResult",
    "GetConversationQuery",
    "ListConversationsQuery",
    "ListMessagesQuery",
    "MessageInvalid",
    "MessageResult",
    "MessageSender",
    "MessagesResult",
    "PreparedUserMessageResult",
    "RecordElfieMessageCommand",
    "RecordedElfieMessageResult",
    "RecordUserMessageCommand",
    "StoredConversationMessage",
)
