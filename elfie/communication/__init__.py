"""精灵自带的双向消息通信能力。"""

from elfie.communication.channel import (
    CommunicationChannel,
    CommunicationMessage,
    LegacyCommunicationChannel,
    MessageDirection,
    MessageKind,
)
from elfie.communication.channels import (
    TelegramChannel,
    TelegramConnector,
    WeChatChannel,
    WeChatConnector,
)
from elfie.communication.contracts import (
    AudioPart,
    CommunicationEnvelope,
    ContentPart,
    DeliveryReceipt,
    DeliveryStatus,
    FilePart,
    ImagePart,
    InboundDisposition,
    InboundDispositionStatus,
    ReactionPart,
    SystemEventPart,
    TextPart,
)
from elfie.communication.hub import CommunicationHub
from elfie.communication.inbox import CommunicationInbox
from elfie.communication.outbox import (
    CommunicationOutbox,
    OutboxEntry,
)
from elfie.communication.policy import CommunicationPolicy, CommunicationPolicyError
from elfie.communication.router import (
    ChannelRegistrationError,
    CommunicationRouter,
)

__all__ = [
    "CommunicationChannel",
    "LegacyCommunicationChannel",
    "CommunicationMessage",
    "CommunicationEnvelope",
    "ContentPart",
    "MessageDirection",
    "MessageKind",
    "TextPart",
    "ImagePart",
    "AudioPart",
    "FilePart",
    "ReactionPart",
    "SystemEventPart",
    "InboundDisposition",
    "InboundDispositionStatus",
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
