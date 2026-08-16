"""Strict HTTP DTOs for one Elfie's Discord account."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from app.features.communication import DiscordAccountResult, DiscordPairingSessionResult


class DiscordAccountUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bot_token: StrictStr = Field(min_length=10, max_length=512)


class DiscordAccountResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    elfie_id: str
    state: str
    bot_username: Optional[str]
    bot_display_name: Optional[str]
    bound_discord_username: Optional[str]
    bound_display_name: Optional[str]
    last_checked_at: Optional[str]
    issue: Optional[str]

    @classmethod
    def from_result(cls, result: DiscordAccountResult) -> DiscordAccountResponse:
        return cls(**result.__dict__)


class DiscordPairingSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invite_url: StrictStr
    bot_profile_url: StrictStr
    pairing_code: StrictStr
    expires_at: StrictStr

    @classmethod
    def from_result(
        cls, result: DiscordPairingSessionResult
    ) -> DiscordPairingSessionResponse:
        return cls(**result.__dict__)


class DiscordAccountErrorDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DiscordAccountErrorItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: DiscordAccountErrorDetails


class DiscordAccountErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: DiscordAccountErrorItem


__all__ = tuple(name for name in globals() if name.endswith(("Request", "Response")))
