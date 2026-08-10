"""Persistence boundary for account and ownership queries used by API runtimes."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.infrastructure.persistence.elfie_repository import ElfieRecord, ElfieRepository
from infrastructure.persistence.store import get_db


@dataclass(frozen=True)  # CPython 3.9 uses explicit __slots__ below.
class RuntimeAccount:
    """Account fields exposed to the authenticated API runtime."""

    user_id: int
    account_id: str
    password_hash: str
    role: str
    display_name: str | None
    avatar_color: int
    avatar_kind: str
    avatar_path: str | None
    gender: str
    birth_date: str | None
    default_landing_page: str
    theme_key: str
    created_at: str
    __slots__ = (
        "user_id",
        "account_id",
        "password_hash",
        "role",
        "display_name",
        "avatar_color",
        "avatar_kind",
        "avatar_path",
        "gender",
        "birth_date",
        "default_landing_page",
        "theme_key",
        "created_at",
    )


class RuntimeQueryRepository:
    """Own final-root SQL needed by API and WebSocket adapters."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def find_account_by_account_id(self, account_id: str) -> RuntimeAccount | None:
        """Load one final account by its exact login identifier."""
        with get_db(self._db_path) as connection:
            row = connection.execute(
                f"{_ACCOUNT_SELECT} WHERE account_id=?", (account_id,)
            ).fetchone()
        return None if row is None else _account(row)

    def find_account_by_id(self, user_id: int) -> RuntimeAccount | None:
        """Load one final account by identifier."""
        with get_db(self._db_path) as connection:
            row = connection.execute(
                f"{_ACCOUNT_SELECT} WHERE id=?", (user_id,)
            ).fetchone()
        return None if row is None else _account(row)

    def owner_id_for_elfie(self, elfie_id: str) -> int | None:
        """Return the owner of one final Elfie, if it exists."""
        record = ElfieRepository(self._db_path).get(elfie_id)
        return None if record is None else record.owner_user_id

    def elfie_is_owned_by(self, elfie_id: str, user_id: int) -> bool:
        """Check one final Elfie ownership relation."""
        return (
            ElfieRepository(self._db_path).get_for_owner(
                elfie_id, owner_user_id=user_id
            )
            is not None
        )

    def list_elfies_for_owner(self, user_id: int) -> list[ElfieRecord]:
        """List final Elfies owned by one account."""
        return ElfieRepository(self._db_path).list_for_owner(user_id)


_ACCOUNT_SELECT = """
SELECT id,account_id,password_hash,role,display_name,avatar_color,avatar_kind,
       avatar_path,gender,birth_date,default_landing_page,theme_key,created_at
FROM users
"""


def _account(row: sqlite3.Row) -> RuntimeAccount:
    return RuntimeAccount(
        user_id=int(row["id"]),
        account_id=str(row["account_id"]),
        password_hash=str(row["password_hash"]),
        role=str(row["role"]),
        display_name=(
            None if row["display_name"] is None else str(row["display_name"])
        ),
        avatar_color=int(row["avatar_color"]),
        avatar_kind=str(row["avatar_kind"]),
        avatar_path=None if row["avatar_path"] is None else str(row["avatar_path"]),
        gender="male" if row["gender"] is None else str(row["gender"]),
        birth_date=None if row["birth_date"] is None else str(row["birth_date"]),
        default_landing_page=str(row["default_landing_page"]),
        theme_key=str(row["theme_key"]),
        created_at=str(row["created_at"]),
    )


__all__ = ("RuntimeAccount", "RuntimeQueryRepository")
