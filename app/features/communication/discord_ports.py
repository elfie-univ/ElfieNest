"""Consumer-owned boundaries for Discord account product use-cases."""

from __future__ import annotations

from typing import Optional, Protocol, Tuple

from app.features.accounts import AccountPrincipal

from .discord_port_models import (
    DiscordBotInspection,
    StoredDiscordAccount,
    StoredDiscordBinding,
)


class DiscordAccountPortError(RuntimeError):
    """Discord account persistence could not complete an operation."""


class DiscordAccountStoreConflict(DiscordAccountPortError):
    """A Discord bot identity is already attached to another Elfie."""


class DiscordBotInspectionError(RuntimeError):
    """Base sanitized Discord Bot API inspection failure."""


class DiscordBotTokenRejected(DiscordBotInspectionError):
    """Discord rejected the supplied bot credential."""


class DiscordBotTransportError(DiscordBotInspectionError):
    """Discord could not be reached safely."""


class DiscordAccountStorePort(Protocol):
    def owner_user_id(self, elfie_id: str) -> Optional[int]: ...

    def get_account(self, elfie_id: str) -> Optional[StoredDiscordAccount]: ...

    def list_active_accounts(self) -> Tuple[StoredDiscordAccount, ...]: ...

    def save_account(self, account: StoredDiscordAccount) -> None: ...

    def mark_account_health(
        self,
        elfie_id: str,
        *,
        status: str,
        checked_at: str,
        issue: Optional[str],
    ) -> None: ...

    def disconnect_account(self, elfie_id: str, *, disconnected_at: str) -> None: ...

    def replace_binding(self, binding: StoredDiscordBinding) -> None: ...

    def get_binding(self, elfie_id: str) -> Optional[StoredDiscordBinding]: ...


class DiscordTokenPort(Protocol):
    def credential_ref(self, elfie_id: str) -> str: ...

    def load(self, credential_ref: str) -> str: ...

    def replace(self, elfie_id: str, token: str) -> str: ...

    def delete(self, elfie_id: str) -> None: ...


class DiscordBotInspectionPort(Protocol):
    def inspect_bot(self, bot_token: str) -> DiscordBotInspection: ...


class DiscordBotAvatarPort(Protocol):
    def sync_avatar(self, bot_token: str, content: bytes, media_type: str) -> None: ...


class DiscordAccountPrincipalLookupPort(Protocol):
    def find_principal(self, user_id: int) -> Optional[AccountPrincipal]: ...


__all__ = (
    "DiscordAccountPortError",
    "DiscordAccountPrincipalLookupPort",
    "DiscordAccountStoreConflict",
    "DiscordAccountStorePort",
    "DiscordBotInspectionError",
    "DiscordBotInspectionPort",
    "DiscordBotAvatarPort",
    "DiscordBotTokenRejected",
    "DiscordBotTransportError",
    "DiscordTokenPort",
)
