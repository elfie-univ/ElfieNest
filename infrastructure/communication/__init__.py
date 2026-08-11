"""Technical adapters for product message transport."""

from .channels import TelegramChannel, TelegramConnector, WeChatChannel, WeChatConnector
from .elfie_delivery import ElfieMessageDeliveryAdapter, OwnerMessageSession
from .same_origin import SameOriginMessagePublisher

__all__ = (
    "ElfieMessageDeliveryAdapter",
    "OwnerMessageSession",
    "SameOriginMessagePublisher",
    "TelegramChannel",
    "TelegramConnector",
    "WeChatChannel",
    "WeChatConnector",
)
