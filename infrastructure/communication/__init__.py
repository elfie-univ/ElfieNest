"""Technical adapters for product message transport."""

from .channels import TelegramChannel, TelegramConnector, WeChatChannel, WeChatConnector
from .discord import DiscordChannel, DiscordConnector
from .elfie_delivery import (
    ElfieCommunicationChannelAdapter,
    ElfieMessageDeliveryAdapter,
    OwnerMessageSession,
)
from .same_origin import SameOriginMessagePublisher

__all__ = (
    "ElfieMessageDeliveryAdapter",
    "ElfieCommunicationChannelAdapter",
    "OwnerMessageSession",
    "SameOriginMessagePublisher",
    "TelegramChannel",
    "TelegramConnector",
    "DiscordChannel",
    "DiscordConnector",
    "WeChatChannel",
    "WeChatConnector",
)
