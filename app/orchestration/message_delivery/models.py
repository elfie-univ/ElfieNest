"""Commands and results for the existing product message-delivery workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.features.communication import MessageResult


@dataclass(frozen=True)
class SubmitUserMessageCommand:
    elfie_id: str
    text: str
    channel: str = "web"
    external_message_id: Optional[str] = None


@dataclass(frozen=True)
class DeliverElfieReplyCommand:
    elfie_id: str
    text: str
    channel: str = "web"
    meta: str = "实时回复"


@dataclass(frozen=True)
class SubmittedMessageResult:
    message: MessageResult


__all__ = (
    "DeliverElfieReplyCommand",
    "SubmittedMessageResult",
    "SubmitUserMessageCommand",
)
