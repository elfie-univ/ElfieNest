"""Strict HTTP DTOs for one Elfie's Telegram account."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from app.features.communication import (
    TelegramAccountResult,
    TelegramPairingSessionResult,
)


class TelegramAccountUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bot_token: StrictStr = Field(min_length=10, max_length=256)


class TelegramAccountResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    elfie_id: str
    state: str
    bot_username: Optional[str]
    bot_display_name: Optional[str]
    bound_telegram_username: Optional[str]
    bound_display_name: Optional[str]
    last_checked_at: Optional[str]
    issue: Optional[str]

    @classmethod
    def from_result(cls, result: TelegramAccountResult) -> TelegramAccountResponse:
        return cls(**result.__dict__)


class TelegramPairingSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deep_link: str
    expires_at: str

    @classmethod
    def from_result(
        cls, result: TelegramPairingSessionResult
    ) -> TelegramPairingSessionResponse:
        return cls(deep_link=result.deep_link, expires_at=result.expires_at)


class TelegramAccountErrorDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TelegramAccountErrorItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: TelegramAccountErrorDetails


class TelegramAccountErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: TelegramAccountErrorItem


__all__ = tuple(name for name in globals() if name.endswith(("Request", "Response")))
