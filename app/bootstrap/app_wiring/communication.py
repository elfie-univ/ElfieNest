"""Production composition for product conversations and message delivery."""

from __future__ import annotations

from dataclasses import dataclass

from app.features.accounts import AccountsService
from app.features.communication import CommunicationFacade, DiscordAccountsService
from app.features.communication.telegram_service import TelegramAccountsService
from app.features.elfies import ElfiesService
from app.orchestration.message_delivery import (
    DiscordReplyRecorder,
    DiscordUpdateHandler,
    MessageDeliveryFacade,
    TelegramReplyRecorder,
    TelegramUpdateHandler,
)
from infrastructure.communication import (
    ElfieCommunicationChannelAdapter,
    ElfieMessageDeliveryAdapter,
    OwnerMessageSession,
    SameOriginMessagePublisher,
)
from infrastructure.communication.discord.client import (
    DiscordBotAvatarUpdater,
    DiscordBotInspector,
)
from infrastructure.communication.discord.runner import DiscordGatewayRuntime
from infrastructure.communication.telegram.client import (
    TelegramBotAvatarUpdater,
    TelegramBotInspector,
)
from infrastructure.communication.telegram.runner import TelegramLongPollingRuntime
from infrastructure.persistence.configuration.discord_tokens import DiscordTokenAdapter
from infrastructure.persistence.configuration.telegram_tokens import (
    TelegramTokenAdapter,
)
from infrastructure.persistence.elfie_workspace.communication import (
    SQLiteConversationHistoryAdapter,
)
from infrastructure.persistence.elfie_workspace.discord_accounts import (
    SQLiteDiscordAccountStore,
)
from infrastructure.persistence.elfie_workspace.elfies import (
    SQLiteElfiesProjectionAdapter,
)
from infrastructure.persistence.elfie_workspace.telegram_accounts import (
    SQLiteTelegramAccountStore,
)
from infrastructure.persistence.layout.data_home import data_home_from_db_path
from infrastructure.persistence.layout.data_layout import final_root_layout


@dataclass(frozen=True)
class CommunicationServices:
    communication: CommunicationFacade
    message_delivery: MessageDeliveryFacade
    realtime: SameOriginMessagePublisher
    telegram_accounts: TelegramAccountsService
    telegram_runtime: TelegramLongPollingRuntime
    discord_accounts: DiscordAccountsService
    discord_runtime: DiscordGatewayRuntime


def build_communication_services(
    db_path: str,
    *,
    accounts: AccountsService,
    elfies: ElfiesService,
    session: OwnerMessageSession | None,
) -> CommunicationServices:
    history = SQLiteConversationHistoryAdapter(db_path)
    communication = CommunicationFacade(history, elfies)
    realtime = SameOriginMessagePublisher(
        lambda token, user_id: (
            (principal := accounts.authenticate_session(token)) is not None
            and principal.user_id == user_id
        )
    )
    message_delivery = MessageDeliveryFacade(
        communication,
        ElfieMessageDeliveryAdapter(session),
        realtime,
    )
    telegram_store = SQLiteTelegramAccountStore(db_path)
    portrait_source = SQLiteElfiesProjectionAdapter(db_path)
    telegram_tokens = TelegramTokenAdapter(
        None
        if db_path == ":memory:"
        else final_root_layout(data_home_from_db_path(db_path)).auth_env
    )
    telegram_accounts = TelegramAccountsService(
        telegram_store,
        telegram_tokens,
        TelegramBotInspector(),
        accounts,
        portrait_source=portrait_source,
        avatar_sync=TelegramBotAvatarUpdater(),
    )
    telegram_handler = TelegramUpdateHandler(
        telegram_accounts,
        message_delivery,
        communication,
    )
    telegram_runtime = TelegramLongPollingRuntime(
        source=telegram_accounts,
        handler=telegram_handler,
        registry=ElfieCommunicationChannelAdapter(session),
        history=TelegramReplyRecorder(communication),
    )
    discord_store = SQLiteDiscordAccountStore(db_path)
    discord_tokens = DiscordTokenAdapter(
        None
        if db_path == ":memory:"
        else final_root_layout(data_home_from_db_path(db_path)).auth_env
    )
    discord_accounts = DiscordAccountsService(
        discord_store,
        discord_tokens,
        DiscordBotInspector(),
        accounts,
        portrait_source=portrait_source,
        avatar_sync=DiscordBotAvatarUpdater(),
    )
    discord_handler = DiscordUpdateHandler(
        discord_accounts,
        message_delivery,
        communication,
    )
    discord_runtime = DiscordGatewayRuntime(
        source=discord_accounts,
        handler=discord_handler,
        registry=ElfieCommunicationChannelAdapter(session),
        history=DiscordReplyRecorder(communication),
    )
    return CommunicationServices(
        communication=communication,
        message_delivery=message_delivery,
        realtime=realtime,
        telegram_accounts=telegram_accounts,
        telegram_runtime=telegram_runtime,
        discord_accounts=discord_accounts,
        discord_runtime=discord_runtime,
    )


__all__ = ("CommunicationServices", "build_communication_services")
