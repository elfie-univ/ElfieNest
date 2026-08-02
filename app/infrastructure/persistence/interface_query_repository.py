"""Final persistence projections used by HTTP interface adapters."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.features.accounts.roles import AccountRole, parse_account_role
from app.infrastructure.persistence.account_repository import (
    ACCOUNT_ID_MAX_LENGTH,
    ACCOUNT_ID_MIN_LENGTH,
    DISPLAY_NAME_MAX_LENGTH,
)
from app.infrastructure.persistence.store import get_db


@dataclass(frozen=True)
class InterfaceUserRecord:
    """One account row with its current final Elfie count."""

    user_id: int
    account_id: str  # 登录账号
    display_name: str | None  # 显示名称
    role: AccountRole
    created_at: str
    avatar_path: str | None
    elfie_limit: int | None
    elfie_count: int
    gender: str | None
    birth_date: str | None
    presence: str
    last_seen_at: str | None
    language: str


@dataclass(frozen=True)
class InterfaceElfieRecord:
    """Final Elfie projection required by user and Owner HTTP routes."""

    elfie_id: str
    name: str
    owner_user_id: int
    owner_account_id: str
    owner_display_name: str | None
    species: str
    gender: str | None
    birth_date: str | None
    adopted_at: str
    bed_number: int | None
    status: str
    summary: str | None


class InterfaceQueryRepository:
    """Own cross-table SQL needed by thin HTTP adapters."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def update_avatar_path(self, user_id: int, avatar_path: str) -> None:
        with get_db(self._db_path) as connection:
            connection.execute(
                "UPDATE users SET avatar_path=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (avatar_path, user_id),
            )
            connection.commit()

    def get_user(self, user_id: int) -> InterfaceUserRecord | None:
        with get_db(self._db_path) as connection:
            row = connection.execute(
                f"{_USER_SELECT} WHERE users.id=?", (user_id,)
            ).fetchone()
        return None if row is None else _user_record(row)

    def list_members(self, excluding_user_id: int) -> tuple[InterfaceUserRecord, ...]:
        with get_db(self._db_path) as connection:
            rows = connection.execute(
                f"{_USER_SELECT} WHERE users.id!=? ORDER BY users.id",
                (excluding_user_id,),
            ).fetchall()
        return tuple(_user_record(row) for row in rows)

    def list_all_users(self) -> tuple[InterfaceUserRecord, ...]:
        """Return every account, including the read-only Owner row."""
        with get_db(self._db_path) as connection:
            rows = connection.execute(f"{_USER_SELECT} ORDER BY users.id").fetchall()
        return tuple(_user_record(row) for row in rows)

    def update_member_limit(self, user_id: int, limit: int | None) -> bool:
        """Update only the adoption limit for a mutable member account."""
        with get_db(self._db_path) as connection:
            cursor = connection.execute(
                """UPDATE users SET elfie_limit=?,updated_at=CURRENT_TIMESTAMP
                   WHERE id=? AND role IN ('admin','user')""",
                (limit, user_id),
            )
            connection.commit()
        return cursor.rowcount == 1

    def create_member(
        self,
        *,
        account_id: str,
        display_name: str | None,
        password_hash: str,
        role: AccountRole,
    ) -> int | None:
        normalized_account_id, normalized_display_name = _normalize_member_identity(
            account_id, display_name
        )
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = connection.execute(
                    """INSERT INTO users
                       (account_id,display_name,password_hash,role)
                       VALUES (?,?,?,?)""",
                    (
                        normalized_account_id,
                        normalized_display_name,
                        password_hash,
                        role,
                    ),
                )
            except sqlite3.IntegrityError as error:
                connection.rollback()
                if "maximum" in str(error):
                    raise MemberCapacityError(str(error)) from error
                return None
            connection.commit()
        return None if cursor.lastrowid is None else int(cursor.lastrowid)

    def reset_member_password_and_revoke_sessions(
        self, user_id: int, password_hash: str
    ) -> None:
        """Atomically replace a member password and revoke all its sessions."""
        with get_db(self._db_path) as connection:
            cursor = connection.execute(
                """UPDATE users SET password_hash=?,updated_at=CURRENT_TIMESTAMP
                   WHERE id=? AND role IN ('admin','user')""",
                (password_hash, user_id),
            )
            if cursor.rowcount != 1:
                raise MemberMutationTargetError(user_id)
            connection.execute(
                """UPDATE sessions SET revoked_at=COALESCE(revoked_at,CURRENT_TIMESTAMP)
                   WHERE user_id=?""",
                (user_id,),
            )
            connection.commit()

    def delete_member(self, user_id: int) -> bool:
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM sessions WHERE user_id=? "
                "AND EXISTS (SELECT 1 FROM users WHERE id=? AND role IN ('admin','user'))",
                (user_id, user_id),
            )
            cursor = connection.execute(
                "DELETE FROM users WHERE id=? AND role IN ('admin','user') "
                "AND NOT EXISTS (SELECT 1 FROM elfies WHERE owner_user_id=?)",
                (user_id, user_id),
            )
            connection.commit()
        return cursor.rowcount == 1

    def list_elfies(
        self,
        *,
        owner_user_id: int | None = None,
        species: str | None = None,
    ) -> tuple[InterfaceElfieRecord, ...]:
        clauses: list[str] = []
        parameters: list[str | int] = []
        if owner_user_id is not None:
            clauses.append("elfies.owner_user_id=?")
            parameters.append(owner_user_id)
        if species is not None:
            clauses.append("elfies.species=?")
            parameters.append(species)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with get_db(self._db_path) as connection:
            rows = connection.execute(
                _ELFIE_SELECT + where + " ORDER BY elfies.adopted_at DESC",
                parameters,
            ).fetchall()
        return tuple(_elfie_record(row) for row in rows)

    def get_elfie(
        self, elfie_id: str, *, owner_user_id: int | None = None
    ) -> InterfaceElfieRecord | None:
        query = _ELFIE_SELECT + " WHERE elfies.elfie_id=?"
        parameters: tuple[str | int, ...] = (elfie_id,)
        if owner_user_id is not None:
            query += " AND elfies.owner_user_id=?"
            parameters = (elfie_id, owner_user_id)
        with get_db(self._db_path) as connection:
            row = connection.execute(query, parameters).fetchone()
        return None if row is None else _elfie_record(row)


_USER_SELECT = """
SELECT users.id,users.account_id,users.display_name,users.role,users.created_at,
       users.avatar_path,users.elfie_limit,users.gender,users.birth_date,
       users.presence,users.last_seen_at,users.language,
       (SELECT COUNT(*) FROM elfies WHERE elfies.owner_user_id=users.id) AS elfie_count
FROM users
"""

_ELFIE_SELECT = """
SELECT elfies.elfie_id,elfies.name,elfies.owner_user_id,
       users.account_id AS owner_account_id,
       users.display_name AS owner_display_name,
       elfies.species,elfies.gender,elfies.birth_date,elfies.adopted_at,
       elfies.bed_number,elfies.status,elfies.summary
FROM elfies JOIN users ON users.id=elfies.owner_user_id
"""


def _user_record(row: sqlite3.Row) -> InterfaceUserRecord:
    return InterfaceUserRecord(
        user_id=int(row["id"]),
        account_id=str(row["account_id"]),
        display_name=None if row["display_name"] is None else str(row["display_name"]),
        role=parse_account_role(str(row["role"])),
        created_at=str(row["created_at"]),
        avatar_path=None if row["avatar_path"] is None else str(row["avatar_path"]),
        elfie_limit=None if row["elfie_limit"] is None else int(row["elfie_limit"]),
        elfie_count=int(row["elfie_count"]),
        gender=None if row["gender"] is None else str(row["gender"]),
        birth_date=None if row["birth_date"] is None else str(row["birth_date"]),
        presence=str(row["presence"]),
        last_seen_at=(
            None if row["last_seen_at"] is None else str(row["last_seen_at"])
        ),
        language=str(row["language"]),
    )


class MemberIdentityValidationError(ValueError):
    """A member identity violates the final account contract."""


class MemberCapacityError(RuntimeError):
    """A role or total-account capacity rejected a member insert."""


class MemberMutationTargetError(RuntimeError):
    """A password reset did not target exactly one mutable member."""

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id
        super().__init__(f"member {user_id} is not mutable")


def _normalize_member_identity(
    account_id: str, display_name: str | None
) -> tuple[str, str | None]:
    normalized_account_id = account_id.strip()
    if not ACCOUNT_ID_MIN_LENGTH <= len(normalized_account_id) <= ACCOUNT_ID_MAX_LENGTH:
        raise MemberIdentityValidationError
    if display_name is None:
        return normalized_account_id, None
    normalized_display_name = display_name.strip()
    if not normalized_display_name:
        return normalized_account_id, None
    if len(normalized_display_name) > DISPLAY_NAME_MAX_LENGTH:
        raise MemberIdentityValidationError
    return normalized_account_id, normalized_display_name


def _elfie_record(row: sqlite3.Row) -> InterfaceElfieRecord:
    return InterfaceElfieRecord(
        elfie_id=str(row["elfie_id"]),
        name=str(row["name"]),
        owner_user_id=int(row["owner_user_id"]),
        owner_account_id=str(row["owner_account_id"]),
        owner_display_name=(
            None
            if row["owner_display_name"] is None
            else str(row["owner_display_name"])
        ),
        species=str(row["species"]),
        gender=None if row["gender"] is None else str(row["gender"]),
        birth_date=None if row["birth_date"] is None else str(row["birth_date"]),
        adopted_at=str(row["adopted_at"]),
        bed_number=None if row["bed_number"] is None else int(row["bed_number"]),
        status=str(row["status"]),
        summary=None if row["summary"] is None else str(row["summary"]),
    )


__all__ = (
    "InterfaceElfieRecord",
    "InterfaceQueryRepository",
    "InterfaceUserRecord",
    "MemberCapacityError",
    "MemberIdentityValidationError",
    "MemberMutationTargetError",
)
