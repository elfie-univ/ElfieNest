"""Technical records used by message-delivery Ports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from app.features.communication import MessageResult

DeliveryAdmissionStatus = Literal[
    "accepted",
    "duplicate",
    "rejected",
    "unavailable",
]


@dataclass(frozen=True)
class UserMessageDeliveryAttempt:
    elfie_id: str
    text: str
    owner_user_id: int
    owner_account_id: str
    conversation_id: str
    channel_id: str
    external_message_id: Optional[str]


@dataclass(frozen=True)
class DeliveryAdmission:
    status: DeliveryAdmissionStatus
    error_code: Optional[str] = None
    retryable: bool = False


@dataclass(frozen=True)
class LiveConversationMessage:
    owner_user_id: int
    message: MessageResult


__all__ = (
    "DeliveryAdmission",
    "DeliveryAdmissionStatus",
    "LiveConversationMessage",
    "UserMessageDeliveryAttempt",
)
