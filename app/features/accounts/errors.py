"""Stable business errors raised by the Accounts facade."""

from __future__ import annotations


class AccountsError(RuntimeError):
    pass


class AuthenticationFailed(AccountsError):
    pass


class LoginRateLimited(AccountsError):
    pass


class AccountForbidden(AccountsError):
    pass


__all__ = (
    "AccountForbidden",
    "AccountsError",
    "AuthenticationFailed",
    "LoginRateLimited",
)
