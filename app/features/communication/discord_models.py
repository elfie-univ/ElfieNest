"""Commands and results for the owner-managed Discord product flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from app.features.accounts import AccountPrincipal

DiscordAccountState = Literal[
    "unconfigured",
    "waiting_pairing",
    "active",
    "attention",
]


@dataclass(frozen=True)
class GetDiscordAccountQuery:
    elfie_id: str


@dataclass(frozen=True)
class ConfigureDiscordAccountCommand:
    elfie_id: str
    bot_token: str


@dataclass(frozen=True)
class DisconnectDiscordAccountCommand:
    elfie_id: str


@dataclass(frozen=True)
class CreateDiscordPairingSessionCommand:
    elfie_id: str


@dataclass(frozen=True)
class DiscordAccountResult:
    elfie_id: str
    state: DiscordAccountState
    bot_username: Optional[str]
    bot_display_name: Optional[str]
    bound_discord_username: Optional[str]
    bound_display_name: Optional[str]
    last_checked_at: Optional[str]
    issue: Optional[str]


@dataclass(frozen=True)
class DiscordPairingSessionResult:
    invite_url: str
    bot_profile_url: str
    pairing_code: str
    expires_at: str


@dataclass(frozen=True)
class DiscordPairingCompletion:
    completed: bool
    reason: Optional[str] = None


@dataclass(frozen=True)
class AuthorizedDiscordMessage:
    elfie_id: str
    principal: AccountPrincipal
    conversation_id: str
    external_actor_id: str
    external_actor_display_name: str


__all__ = (
    "AuthorizedDiscordMessage",
    "ConfigureDiscordAccountCommand",
    "CreateDiscordPairingSessionCommand",
    "DisconnectDiscordAccountCommand",
    "DiscordAccountResult",
    "DiscordAccountState",
    "DiscordPairingCompletion",
    "DiscordPairingSessionResult",
    "GetDiscordAccountQuery",
)
