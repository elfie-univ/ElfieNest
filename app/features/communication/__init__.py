"""Public facade for product conversations and user-visible message history."""

from .avatar_ports import ElfiePortraitPort
from .discord_errors import (
    DiscordAccountConflict,
    DiscordAccountError,
    DiscordAccountInvalid,
    DiscordAccountNotFound,
    DiscordAccountUnavailable,
)
from .discord_models import (
    AuthorizedDiscordMessage,
    ConfigureDiscordAccountCommand,
    CreateDiscordPairingSessionCommand,
    DisconnectDiscordAccountCommand,
    DiscordAccountResult,
    DiscordAccountState,
    DiscordPairingCompletion,
    DiscordPairingSessionResult,
    GetDiscordAccountQuery,
)
from .discord_port_models import (
    DiscordBotInspection,
    DiscordPrivateUpdate,
    DiscordRuntimeAccount,
    StoredDiscordAccount,
    StoredDiscordBinding,
)
from .discord_ports import DiscordBotAvatarPort
from .discord_service import DiscordAccountsService
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
from .telegram_errors import (
    TelegramAccountConflict,
    TelegramAccountError,
    TelegramAccountInvalid,
    TelegramAccountNotFound,
    TelegramAccountUnavailable,
)
from .telegram_models import (
    AuthorizedTelegramMessage,
    ConfigureTelegramAccountCommand,
    CreateTelegramPairingSessionCommand,
    DisconnectTelegramAccountCommand,
    GetTelegramAccountQuery,
    TelegramAccountResult,
    TelegramAccountState,
    TelegramPairingCompletion,
    TelegramPairingSessionResult,
)
from .telegram_port_models import (
    StoredTelegramAccount,
    StoredTelegramBinding,
    TelegramBotInspection,
    TelegramPrivateUpdate,
    TelegramRuntimeAccount,
)
from .telegram_ports import TelegramBotAvatarPort
from .telegram_service import TelegramAccountsService

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
    "AuthorizedTelegramMessage",
    "ConfigureTelegramAccountCommand",
    "CreateTelegramPairingSessionCommand",
    "DisconnectTelegramAccountCommand",
    "GetTelegramAccountQuery",
    "StoredTelegramAccount",
    "StoredTelegramBinding",
    "TelegramAccountConflict",
    "TelegramAccountError",
    "TelegramAccountInvalid",
    "TelegramAccountNotFound",
    "TelegramAccountResult",
    "TelegramAccountState",
    "TelegramAccountUnavailable",
    "TelegramAccountsService",
    "TelegramBotAvatarPort",
    "TelegramBotInspection",
    "TelegramPairingCompletion",
    "TelegramPairingSessionResult",
    "TelegramPrivateUpdate",
    "TelegramRuntimeAccount",
    "AuthorizedDiscordMessage",
    "ConfigureDiscordAccountCommand",
    "CreateDiscordPairingSessionCommand",
    "DisconnectDiscordAccountCommand",
    "DiscordAccountConflict",
    "DiscordAccountError",
    "DiscordAccountInvalid",
    "DiscordAccountNotFound",
    "DiscordAccountResult",
    "DiscordAccountState",
    "DiscordAccountUnavailable",
    "DiscordAccountsService",
    "DiscordBotAvatarPort",
    "DiscordBotInspection",
    "DiscordPairingCompletion",
    "DiscordPairingSessionResult",
    "DiscordPrivateUpdate",
    "DiscordRuntimeAccount",
    "ElfiePortraitPort",
    "GetDiscordAccountQuery",
    "StoredDiscordAccount",
    "StoredDiscordBinding",
)
