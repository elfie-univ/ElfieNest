"""Canonical account roles and strict hierarchy predicates."""

from __future__ import annotations

from typing import Final, Literal

from typing_extensions import TypeAlias

AccountRole: TypeAlias = Literal["owner", "admin", "user"]

MAX_ADMINS: Final[int] = 5
MAX_ACCOUNTS: Final[int] = 16
_MANAGER_ROLES: Final[frozenset[AccountRole]] = frozenset({"owner", "admin"})


class AccountRoleError(ValueError):
    """Raised when persisted role data is outside the canonical role set."""

    def __init__(self, raw_role: str) -> None:
        self.raw_role = raw_role
        super().__init__(raw_role)

    def __str__(self) -> str:
        return f"unsupported account role: {self.raw_role!r}"


def parse_account_role(raw_role: str) -> AccountRole:
    """Parse one role loaded from a persistence or HTTP boundary."""
    if raw_role == "owner":
        return "owner"
    if raw_role == "admin":
        return "admin"
    if raw_role == "user":
        return "user"
    raise AccountRoleError(raw_role)


def role_rank(role: AccountRole) -> int:
    """Return the immutable management rank for one canonical role."""
    if role == "owner":
        return 3
    if role == "admin":
        return 2
    if role == "user":
        return 1
    raise AccountRoleError(role)


def is_manager(role: AccountRole) -> bool:
    """Return whether a role may enter the shared management surface."""
    return role in _MANAGER_ROLES


def can_manage_role(actor_role: AccountRole, target_role: AccountRole) -> bool:
    """Return whether an actor may mutate a strictly lower role."""
    return role_rank(actor_role) > role_rank(target_role)


__all__ = (
    "AccountRole",
    "AccountRoleError",
    "MAX_ACCOUNTS",
    "MAX_ADMINS",
    "can_manage_role",
    "is_manager",
    "parse_account_role",
    "role_rank",
)
