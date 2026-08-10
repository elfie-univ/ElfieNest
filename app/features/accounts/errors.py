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


class AccountsUnavailable(AccountsError):
    pass


class AccountNotFound(AccountsError):
    pass


class AccountConflict(AccountsError):
    pass


class AccountValidationFailed(AccountsError):
    pass


class CurrentPasswordIncorrect(AccountsError):
    pass


class PasswordReuseRejected(AccountsError):
    pass


class ManagedAccountCapacityReached(AccountsError):
    pass


class ManagedAccountHasElfies(AccountsError):
    pass


class InvalidAvatar(AccountsError):
    pass


class AvatarTooLarge(InvalidAvatar):
    pass


class AvatarMediaTypeUnsupported(InvalidAvatar):
    pass


class AvatarContentInvalid(InvalidAvatar):
    pass


class AvatarNotFound(AccountsError):
    pass


__all__ = (
    "AccountConflict",
    "AccountForbidden",
    "AccountNotFound",
    "AccountValidationFailed",
    "AccountsError",
    "AccountsUnavailable",
    "AuthenticationFailed",
    "AvatarNotFound",
    "AvatarContentInvalid",
    "AvatarMediaTypeUnsupported",
    "AvatarTooLarge",
    "CurrentPasswordIncorrect",
    "InvalidAvatar",
    "LoginRateLimited",
    "ManagedAccountCapacityReached",
    "ManagedAccountHasElfies",
    "PasswordReuseRejected",
)
