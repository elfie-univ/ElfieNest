"""Consumer-owned boundaries for Telegram account product use-cases."""

from __future__ import annotations

from typing import Optional, Protocol, Tuple

from app.features.accounts import AccountPrincipal

from .telegram_port_models import (
    StoredTelegramAccount,
    StoredTelegramBinding,
    TelegramBotInspection,
)


class TelegramAccountPortError(RuntimeError):
    """Telegram account persistence could not complete an operation."""


class TelegramAccountStoreConflict(TelegramAccountPortError):
    """A platform identity is already attached to another Elfie."""


class TelegramBotInspectionError(RuntimeError):
    """Base sanitized Telegram Bot API inspection failure."""


class TelegramBotTokenRejected(TelegramBotInspectionError):
    """Telegram rejected the supplied bot token."""


class TelegramBotTransportError(TelegramBotInspectionError):
    """Telegram could not be reached safely."""


class TelegramAccountStorePort(Protocol):
    def owner_user_id(self, elfie_id: str) -> Optional[int]: ...

    def get_account(self, elfie_id: str) -> Optional[StoredTelegramAccount]: ...

    def list_active_accounts(self) -> Tuple[StoredTelegramAccount, ...]: ...

    def save_account(self, account: StoredTelegramAccount) -> None: ...

    def mark_account_health(
        self,
        elfie_id: str,
        *,
        status: str,
        checked_at: str,
        issue: Optional[str],
    ) -> None: ...

    def disconnect_account(self, elfie_id: str, *, disconnected_at: str) -> None: ...

    def replace_binding(self, binding: StoredTelegramBinding) -> None: ...

    def get_binding(self, elfie_id: str) -> Optional[StoredTelegramBinding]: ...

    def next_update_id(self, elfie_id: str) -> Optional[int]: ...

    def save_next_update_id(
        self, elfie_id: str, *, next_update_id: int, synced_at: str
    ) -> None: ...


class TelegramTokenPort(Protocol):
    def credential_ref(self, elfie_id: str) -> str: ...

    def load(self, credential_ref: str) -> str: ...

    def replace(self, elfie_id: str, token: str) -> str: ...

    def delete(self, elfie_id: str) -> None: ...


class TelegramBotInspectionPort(Protocol):
    def inspect_bot(self, bot_token: str) -> TelegramBotInspection: ...


class TelegramBotAvatarPort(Protocol):
    def sync_avatar(self, bot_token: str, content: bytes, media_type: str) -> None: ...


class AccountPrincipalLookupPort(Protocol):
    def find_principal(self, user_id: int) -> Optional[AccountPrincipal]: ...


__all__ = (
    "AccountPrincipalLookupPort",
    "TelegramAccountPortError",
    "TelegramAccountStoreConflict",
    "TelegramAccountStorePort",
    "TelegramBotInspectionPort",
    "TelegramBotInspectionError",
    "TelegramBotTokenRejected",
    "TelegramBotTransportError",
    "TelegramBotAvatarPort",
    "TelegramTokenPort",
)
