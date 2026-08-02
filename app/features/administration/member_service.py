"""Owner-only member creation and one-time password reset orchestration."""

from __future__ import annotations

import secrets
import string
from typing import Final, NamedTuple

from app.features.accounts.auth import hash_password
from app.infrastructure.persistence.interface_query_repository import (
    InterfaceQueryRepository,
)

_TEMPORARY_PASSWORD_LENGTH: Final = 12
_TEMPORARY_PASSWORD_ALPHABET: Final = string.ascii_letters + string.digits


class MemberAccountConflictError(RuntimeError):
    """A requested member account identifier already exists."""


class TemporaryPasswordResult(NamedTuple):
    """One-time plaintext returned only to the successful HTTP caller."""

    temporary_password: str


class MemberService:
    """Coordinate member administration without owning persistence SQL."""

    def __init__(self, db_path: str) -> None:
        self._repository = InterfaceQueryRepository(db_path)

    def create_member(
        self,
        *,
        account_id: str,
        display_name: str | None,
        password: str,
    ) -> int:
        user_id = self._repository.create_member(
            account_id=account_id,
            display_name=display_name,
            password_hash=hash_password(password),
        )
        if user_id is None:
            raise MemberAccountConflictError
        return user_id

    def reset_password(self, user_id: int) -> TemporaryPasswordResult:
        temporary_password = "".join(
            secrets.choice(_TEMPORARY_PASSWORD_ALPHABET)
            for _ in range(_TEMPORARY_PASSWORD_LENGTH)
        )
        self._repository.reset_member_password_and_revoke_sessions(
            user_id, hash_password(temporary_password)
        )
        return TemporaryPasswordResult(temporary_password=temporary_password)


__all__ = ("MemberAccountConflictError", "MemberService", "TemporaryPasswordResult")
