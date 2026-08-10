"""Strict models crossing Accounts outbound Ports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from .models import AvatarKind, Gender, LandingPage, Presence, ThemeKey
from .roles import AccountRole


@dataclass(frozen=True)
class AccountProfileRecord:
    user_id: int
    account_id: str
    password_hash: str
    display_name: Optional[str]
    gender: Gender
    birth_date: Optional[str]
    role: AccountRole
    avatar_path: Optional[str]
    avatar_color: int
    avatar_kind: AvatarKind
    theme_key: ThemeKey
    default_landing_page: LandingPage
    created_at: str
    updated_at: str
    elfie_count: int


@dataclass(frozen=True)
class AccountProfileWrite:
    account_id: str
    display_name: Optional[str]
    gender: Gender
    birth_date: Optional[str]
    avatar_color: int
    avatar_kind: AvatarKind


@dataclass(frozen=True)
class ManagedAccountRecord:
    user_id: int
    account_id: str
    display_name: Optional[str]
    role: AccountRole
    gender: Gender
    birth_date: Optional[str]
    presence: Presence
    last_seen_at: Optional[str]
    language: str
    created_at: str
    elfie_count: int
    elfie_quota_override: Optional[int]
    avatar_path: Optional[str]


@dataclass(frozen=True)
class OwnerAccountRecord:
    user_id: int
    account_id: str
    display_name: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]


@dataclass(frozen=True)
class StoredAvatar:
    relative_path: str
    content_type: str
    content: bytes


@dataclass(frozen=True)
class ManagedAccountRecords:
    items: Tuple[ManagedAccountRecord, ...]


__all__ = (
    "AccountProfileRecord",
    "AccountProfileWrite",
    "ManagedAccountRecord",
    "ManagedAccountRecords",
    "OwnerAccountRecord",
    "StoredAvatar",
)
