"""Consumer-owned technical boundaries required by Accounts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .models import AccountPrincipal, SecurityPolicy


@dataclass(frozen=True)
class AccountCredentials:
    user_id: int
    account_id: str
    password_hash: str
    role: str
    display_name: str | None
    default_landing_page: str


class AccountSessionPort(Protocol):
    def find_credentials(self, account_id: str) -> AccountCredentials | None:
        ...

    def issue_session(self, user_id: int, expires_at: datetime) -> str:
        ...

    def find_session(
        self, raw_token: str, now: datetime
    ) -> AccountPrincipal | None:
        ...

    def revoke_session(self, raw_token: str, revoked_at: datetime) -> None:
        ...


class SecurityPolicyPort(Protocol):
    def load(self) -> SecurityPolicy:
        ...


__all__ = ("AccountCredentials", "AccountSessionPort", "SecurityPolicyPort")
