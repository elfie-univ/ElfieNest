"""精灵自带的双向消息通信能力。"""

from elfie.communication.channel import (
    CommunicationChannel,
    CommunicationMessage,
    MessageDirection,
    MessageKind,
)
from elfie.communication.channels import (
    TelegramChannel,
    TelegramConnector,
    WeChatChannel,
    WeChatConnector,
)
from elfie.communication.hub import CommunicationHub
from elfie.communication.inbox import CommunicationInbox
from elfie.communication.outbox import (
    CommunicationOutbox,
    DeliveryReceipt,
    DeliveryStatus,
    OutboxEntry,
)
from elfie.communication.policy import CommunicationPolicy, CommunicationPolicyError
from elfie.communication.router import (
    ChannelRegistrationError,
    CommunicationRouter,
)

__all__ = [
    "CommunicationChannel",
    "CommunicationMessage",
    "MessageDirection",
    "MessageKind",
    "CommunicationInbox",
    "CommunicationOutbox",
    "DeliveryReceipt",
    "DeliveryStatus",
    "OutboxEntry",
    "CommunicationPolicy",
    "CommunicationPolicyError",
    "ChannelRegistrationError",
    "CommunicationRouter",
    "CommunicationHub",
    "WeChatConnector",
    "WeChatChannel",
    "TelegramConnector",
    "TelegramChannel",
]
