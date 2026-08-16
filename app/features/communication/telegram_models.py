"""Commands and results for the owner-managed Telegram product flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from app.features.accounts import AccountPrincipal

TelegramAccountState = Literal[
    "unconfigured",
    "waiting_pairing",
    "active",
    "attention",
]


@dataclass(frozen=True)
class GetTelegramAccountQuery:
    elfie_id: str


@dataclass(frozen=True)
class ConfigureTelegramAccountCommand:
    elfie_id: str
    bot_token: str


@dataclass(frozen=True)
class DisconnectTelegramAccountCommand:
    elfie_id: str


@dataclass(frozen=True)
class CreateTelegramPairingSessionCommand:
    elfie_id: str


@dataclass(frozen=True)
class TelegramAccountResult:
    elfie_id: str
    state: TelegramAccountState
    bot_username: Optional[str]
    bot_display_name: Optional[str]
    bound_telegram_username: Optional[str]
    bound_display_name: Optional[str]
    last_checked_at: Optional[str]
    issue: Optional[str]


@dataclass(frozen=True)
class TelegramPairingSessionResult:
    deep_link: str
    expires_at: str


@dataclass(frozen=True)
class TelegramPairingCompletion:
    completed: bool
    reason: Optional[str] = None


@dataclass(frozen=True)
class AuthorizedTelegramMessage:
    elfie_id: str
    principal: AccountPrincipal
    conversation_id: str
    external_actor_id: str
    external_actor_display_name: str


__all__ = (
    "AuthorizedTelegramMessage",
    "ConfigureTelegramAccountCommand",
    "CreateTelegramPairingSessionCommand",
    "DisconnectTelegramAccountCommand",
    "GetTelegramAccountQuery",
    "TelegramAccountResult",
    "TelegramAccountState",
    "TelegramPairingCompletion",
    "TelegramPairingSessionResult",
)
