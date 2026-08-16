"""Typed records crossing Telegram account and transport Ports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

TelegramStoredStatus = Literal["active", "attention"]


@dataclass(frozen=True)
class StoredTelegramAccount:
    elfie_id: str
    bot_id: str
    bot_username: str
    display_name: str
    credential_ref: str
    configured_owner_user_id: int
    status: TelegramStoredStatus
    last_checked_at: str
    issue: Optional[str]


@dataclass(frozen=True)
class StoredTelegramBinding:
    elfie_id: str
    telegram_user_id: str
    telegram_chat_id: str
    telegram_username: Optional[str]
    display_name: str
    local_owner_user_id: int
    local_owner_account_id: str
    conversation_id: str
    bound_at: str


@dataclass(frozen=True)
class TelegramBotInspection:
    bot_id: str
    username: str
    display_name: str
    webhook_url: str


@dataclass(frozen=True)
class TelegramRuntimeAccount:
    account: StoredTelegramAccount
    bot_token: str
    next_update_id: Optional[int]
    binding: Optional[StoredTelegramBinding] = None


@dataclass(frozen=True)
class TelegramPrivateUpdate:
    update_id: int
    message_id: int
    chat_id: str
    chat_type: str
    telegram_user_id: str
    telegram_username: Optional[str]
    display_name: str
    text: Optional[str]
    sender_is_bot: bool = False


__all__ = (
    "StoredTelegramAccount",
    "StoredTelegramBinding",
    "TelegramBotInspection",
    "TelegramPrivateUpdate",
    "TelegramRuntimeAccount",
    "TelegramStoredStatus",
)
