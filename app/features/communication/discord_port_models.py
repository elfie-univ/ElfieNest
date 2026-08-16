"""Typed records crossing Discord account and transport Ports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

DiscordStoredStatus = Literal["active", "attention"]


@dataclass(frozen=True)
class StoredDiscordAccount:
    elfie_id: str
    bot_id: str
    bot_username: str
    display_name: str
    credential_ref: str
    configured_owner_user_id: int
    status: DiscordStoredStatus
    last_checked_at: str
    issue: Optional[str]


@dataclass(frozen=True)
class StoredDiscordBinding:
    elfie_id: str
    discord_user_id: str
    discord_channel_id: str
    discord_username: Optional[str]
    display_name: str
    local_owner_user_id: int
    local_owner_account_id: str
    conversation_id: str
    bound_at: str


@dataclass(frozen=True)
class DiscordBotInspection:
    bot_id: str
    username: str
    display_name: str


@dataclass(frozen=True)
class DiscordRuntimeAccount:
    account: StoredDiscordAccount
    bot_token: str
    binding: Optional[StoredDiscordBinding] = None


@dataclass(frozen=True)
class DiscordPrivateUpdate:
    message_id: str
    channel_id: str
    discord_user_id: str
    discord_username: Optional[str]
    display_name: str
    text: Optional[str]
    is_dm: bool
    sender_is_bot: bool = False
    guild_id: Optional[str] = None


__all__ = (
    "DiscordBotInspection",
    "DiscordPrivateUpdate",
    "DiscordRuntimeAccount",
    "DiscordStoredStatus",
    "StoredDiscordAccount",
    "StoredDiscordBinding",
)
