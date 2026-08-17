"""Consumer-owned technical boundaries required by Accounts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .models import AccountPrincipal, ManagedAccountRole, SecurityPolicy
from .port_models import (
    AccountProfileRecord,
    AccountProfileWrite,
    ManagedAccountRecord,
    ManagedAccountRecords,
    OwnerAccountRecord,
    StoredAvatar,
)


@dataclass(frozen=True)
class AccountCredentials:
    user_id: int
    account_id: str
    password_hash: str
    role: str
    display_name: str | None
    default_landing_page: str


class AccountSessionPort(Protocol):
    def find_credentials(self, account_id: str) -> AccountCredentials | None: ...

    def issue_session(self, user_id: int, expires_at: datetime) -> str: ...

    def find_session(
        self, raw_token: str, now: datetime
    ) -> AccountPrincipal | None: ...

    def revoke_session(self, raw_token: str, revoked_at: datetime) -> None: ...


class SecurityPolicyPort(Protocol):
    def load(self) -> SecurityPolicy: ...


class InitialOwnerSeedPort(Protocol):
    def seed_initial_owner(self) -> bool: ...


class AccountPersistenceError(RuntimeError):
    """Stable technical failure exposed by the persistence boundary."""


class AccountPersistenceConflict(AccountPersistenceError):
    pass


class AccountPersistenceCapacityError(AccountPersistenceError):
    pass


class AccountPersistenceTargetError(AccountPersistenceError):
    pass


class AccountQuotaPolicyError(RuntimeError):
    pass


class AccountManagementPort(Protocol):
    def create_first_owner(
        self,
        *,
        account_id: str,
        display_name: str | None,
        password_hash: str,
    ) -> OwnerAccountRecord: ...

    def find_profile(self, user_id: int) -> AccountProfileRecord | None: ...

    def record_heartbeat(self, user_id: int, last_seen_at: str) -> bool: ...

    def update_profile(
        self, user_id: int, profile: AccountProfileWrite
    ) -> AccountProfileRecord | None: ...

    def change_password(
        self,
        user_id: int,
        password_hash: str,
        current_session_token: str,
    ) -> None: ...

    def update_theme(self, user_id: int, theme_key: str) -> None: ...

    def update_default_landing_page(self, user_id: int, page: str) -> None: ...

    def update_avatar_path(self, user_id: int, relative_path: str) -> None: ...

    def list_managed_accounts(self) -> ManagedAccountRecords: ...

    def get_managed_account(self, user_id: int) -> ManagedAccountRecord | None: ...

    def create_managed_account(
        self,
        *,
        account_id: str,
        display_name: str | None,
        password_hash: str,
        role: ManagedAccountRole,
    ) -> int: ...

    def create_user_account(
        self,
        *,
        account_id: str,
        display_name: str,
        password_hash: str,
    ) -> int: ...

    def update_managed_quota(self, user_id: int, quota: int | None) -> bool: ...

    def delete_managed_account(self, user_id: int) -> bool: ...

    def reset_managed_password(self, user_id: int, password_hash: str) -> None: ...

    def find_owner_account(self) -> OwnerAccountRecord | None: ...

    def recover_owner_account(
        self,
        user_id: int,
        account_id: str,
        password_hash: str,
    ) -> OwnerAccountRecord | None: ...


class AccountAvatarPort(Protocol):
    def store(
        self, user_id: int, content_type: str, content: bytes
    ) -> StoredAvatar: ...

    def load(self, user_id: int, relative_path: str) -> StoredAvatar | None: ...


class AccountQuotaPolicyPort(Protocol):
    def default_elfie_limit(self) -> int: ...


__all__ = (
    "AccountAvatarPort",
    "AccountCredentials",
    "AccountManagementPort",
    "AccountPersistenceCapacityError",
    "AccountPersistenceConflict",
    "AccountPersistenceError",
    "AccountPersistenceTargetError",
    "AccountQuotaPolicyPort",
    "AccountQuotaPolicyError",
    "AccountSessionPort",
    "InitialOwnerSeedPort",
    "SecurityPolicyPort",
)
