"""精灵自带的双向消息通信能力。"""

from elfie.communication.channel import CommunicationChannel
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
    MessageDirection,
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
from elfie.communication.perception_adapter import (
    AdapterDirectionError,
    CommunicationPerceptionAdapter,
    DeliveryPerceptionCorrelation,
    InboundPerceptionAttempt,
)
from elfie.communication.policy import CommunicationPolicy, CommunicationPolicyError
from elfie.communication.router import (
    ChannelRegistrationError,
    CommunicationRouter,
)

__all__ = [
    "CommunicationChannel",
    "CommunicationEnvelope",
    "ContentPart",
    "MessageDirection",
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
    "AdapterDirectionError",
    "CommunicationPerceptionAdapter",
    "DeliveryPerceptionCorrelation",
    "InboundPerceptionAttempt",
    "ChannelRegistrationError",
    "CommunicationRouter",
    "CommunicationHub",
]
