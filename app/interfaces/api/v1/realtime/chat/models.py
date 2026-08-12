"""Strict WebSocket DTOs for product chat."""

from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from app.features.accounts import AccountRole

_STRICT = ConfigDict(extra="forbid", frozen=True)


class ChatMessageRequest(BaseModel):
    model_config = _STRICT

    event: Literal["user_message"]
    elfie_id: StrictStr
    text: StrictStr = Field(min_length=1, max_length=4000)


class ChatPrincipalResponse(BaseModel):
    model_config = _STRICT

    role: AccountRole
    account_id: StrictStr


class ChatMessageResponse(BaseModel):
    model_config = _STRICT

    id: StrictInt
    elfie_id: StrictStr
    sender: Literal["user", "elfie", "system"]
    text: StrictStr
    created_at: StrictStr


class ChatReadyEvent(BaseModel):
    model_config = _STRICT

    event: Literal["ready"] = "ready"
    principal: ChatPrincipalResponse


class ChatMessageEvent(BaseModel):
    model_config = _STRICT

    event: Literal["message"] = "message"
    message: ChatMessageResponse


class ChatErrorEvent(BaseModel):
    model_config = _STRICT

    event: Literal["error"] = "error"
    detail: StrictStr


ChatServerEvent = Union[ChatReadyEvent, ChatMessageEvent, ChatErrorEvent]

__all__ = (
    "ChatErrorEvent",
    "ChatMessageEvent",
    "ChatMessageRequest",
    "ChatMessageResponse",
    "ChatPrincipalResponse",
    "ChatReadyEvent",
    "ChatServerEvent",
)
