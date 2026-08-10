"""Public models for account authentication and authorization."""

from __future__ import annotations

from dataclasses import dataclass

from .roles import AccountRole


@dataclass(frozen=True)
class AccountPrincipal:
    """Authenticated product identity shared by App entry points."""

    user_id: int
    account_id: str
    role: AccountRole
    default_landing_page: str


@dataclass(frozen=True)
class LoginCommand:
    account_id: str
    password: str
    client_key: str


@dataclass(frozen=True)
class AuthenticatedSession:
    principal: AccountPrincipal
    display_name: str | None
    session_token: str
    ttl_seconds: int


@dataclass(frozen=True)
class SecurityPolicy:
    session_ttl_seconds: int
    max_login_attempts: int
    login_window_seconds: int


__all__ = (
    "AccountPrincipal",
    "AuthenticatedSession",
    "LoginCommand",
    "SecurityPolicy",
)
