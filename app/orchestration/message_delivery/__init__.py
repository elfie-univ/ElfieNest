"""Public facade for authorized message delivery and reply fan-out."""

from .errors import (
    DuplicateMessage,
    MessageDeliveryError,
    MessageDeliveryUnavailable,
    MessageRejected,
)
from .models import (
    DeliverElfieReplyCommand,
    SubmittedMessageResult,
    SubmitUserMessageCommand,
)
from .owner_channel import GodotOwnerChannel, MessageDeliveryOwnerBroadcaster
from .owner_envelope import deliver_owner_message
from .port_models import (
    DeliveryAdmission,
    DeliveryAdmissionStatus,
    LiveConversationMessage,
    UserMessageDeliveryAttempt,
)
from .ports import (
    ElfieMessageDeliveryPort,
    LiveConversationPort,
    MessageDeliveryPortError,
    OwnerMessageBroadcaster,
)
from .service import MessageDeliveryFacade
from .telegram import (
    TelegramReplyRecorder,
    TelegramUpdateHandler,
    TelegramUpdateOutcome,
)

__all__ = (
    "DeliverElfieReplyCommand",
    "DeliveryAdmission",
    "DeliveryAdmissionStatus",
    "DuplicateMessage",
    "ElfieMessageDeliveryPort",
    "LiveConversationMessage",
    "LiveConversationPort",
    "GodotOwnerChannel",
    "MessageDeliveryError",
    "MessageDeliveryFacade",
    "MessageDeliveryOwnerBroadcaster",
    "MessageDeliveryPortError",
    "MessageDeliveryUnavailable",
    "MessageRejected",
    "OwnerMessageBroadcaster",
    "SubmittedMessageResult",
    "SubmitUserMessageCommand",
    "TelegramReplyRecorder",
    "TelegramUpdateHandler",
    "TelegramUpdateOutcome",
    "UserMessageDeliveryAttempt",
    "deliver_owner_message",
)
