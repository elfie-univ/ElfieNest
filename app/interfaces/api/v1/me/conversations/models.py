"""Strict HTTP DTOs for the current member's conversations."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

_STRICT = ConfigDict(extra="forbid", frozen=True)


class ConversationResponse(BaseModel):
    model_config = _STRICT

    elfie_id: StrictStr
    name: StrictStr
    portrait_url: StrictStr
    last_message_preview: StrictStr
    last_message_at: Optional[StrictStr]


class ConversationsResponse(BaseModel):
    model_config = _STRICT

    items: List[ConversationResponse]


class MessageResponse(BaseModel):
    model_config = _STRICT

    id: StrictInt
    elfie_id: StrictStr
    sender: Literal["user", "elfie", "system"]
    text: StrictStr
    created_at: StrictStr


class MessagesResponse(BaseModel):
    model_config = _STRICT

    items: List[MessageResponse]


class MessageCreateRequest(BaseModel):
    model_config = _STRICT

    text: StrictStr = Field(min_length=1, max_length=4000)


class CommunicationErrorDetails(BaseModel):
    model_config = _STRICT


class CommunicationErrorItem(BaseModel):
    model_config = _STRICT

    code: StrictStr
    message: StrictStr
    details: CommunicationErrorDetails


class CommunicationErrorResponse(BaseModel):
    model_config = _STRICT

    error: CommunicationErrorItem


__all__ = (
    "CommunicationErrorDetails",
    "CommunicationErrorItem",
    "CommunicationErrorResponse",
    "ConversationResponse",
    "ConversationsResponse",
    "MessageCreateRequest",
    "MessageResponse",
    "MessagesResponse",
)
