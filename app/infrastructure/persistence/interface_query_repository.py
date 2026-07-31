"""Final persistence projections used by HTTP interface adapters."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.infrastructure.persistence.store import get_db


@dataclass(frozen=True)
class InterfaceUserRecord:
    """One account row with its current final Elfie count."""

    user_id: int
    username: str
    nickname: str | None
    role: str
    created_at: str
    avatar_path: str | None
    elfie_limit: int | None
    elfie_count: int


@dataclass(frozen=True)
class InterfaceElfieRecord:
    """Final Elfie projection required by user and Owner HTTP routes."""

    elfie_id: str
    name: str
    owner_user_id: int
    owner_username: str
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
                f"{_USER_SELECT} WHERE users.id!=? AND users.role='user' ORDER BY users.id",
                (excluding_user_id,),
            ).fetchall()
        return tuple(_user_record(row) for row in rows)

    def create_member(self, username: str, password_hash: str) -> int | None:
        with get_db(self._db_path) as connection:
            try:
                cursor = connection.execute(
                    "INSERT INTO users(username,password_hash,role) VALUES (?,?,'user')",
                    (username, password_hash),
                )
            except sqlite3.IntegrityError:
                return None
            connection.commit()
        return None if cursor.lastrowid is None else int(cursor.lastrowid)

    def update_member_limit(self, user_id: int, limit: int | None) -> None:
        with get_db(self._db_path) as connection:
            connection.execute(
                "UPDATE users SET elfie_limit=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (limit, user_id),
            )
            connection.commit()

    def delete_member(self, user_id: int) -> None:
        with get_db(self._db_path) as connection:
            connection.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            connection.execute("DELETE FROM users WHERE id=?", (user_id,))
            connection.commit()

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
SELECT users.id,users.username,users.nickname,users.role,users.created_at,
       users.avatar_path,users.elfie_limit,
       (SELECT COUNT(*) FROM elfies WHERE elfies.owner_user_id=users.id) AS elfie_count
FROM users
"""

_ELFIE_SELECT = """
SELECT elfies.elfie_id,elfies.name,elfies.owner_user_id,users.username AS owner_username,
       elfies.species,elfies.gender,elfies.birth_date,elfies.adopted_at,
       elfies.bed_number,elfies.status,elfies.summary
FROM elfies JOIN users ON users.id=elfies.owner_user_id
"""


def _user_record(row: sqlite3.Row) -> InterfaceUserRecord:
    return InterfaceUserRecord(
        user_id=int(row["id"]),
        username=str(row["username"]),
        nickname=None if row["nickname"] is None else str(row["nickname"]),
        role=str(row["role"]),
        created_at=str(row["created_at"]),
        avatar_path=None if row["avatar_path"] is None else str(row["avatar_path"]),
        elfie_limit=None if row["elfie_limit"] is None else int(row["elfie_limit"]),
        elfie_count=int(row["elfie_count"]),
    )


def _elfie_record(row: sqlite3.Row) -> InterfaceElfieRecord:
    return InterfaceElfieRecord(
        elfie_id=str(row["elfie_id"]),
        name=str(row["name"]),
        owner_user_id=int(row["owner_user_id"]),
        owner_username=str(row["owner_username"]),
        species=str(row["species"]),
        gender=None if row["gender"] is None else str(row["gender"]),
        birth_date=None if row["birth_date"] is None else str(row["birth_date"]),
        adopted_at=str(row["adopted_at"]),
        bed_number=None if row["bed_number"] is None else int(row["bed_number"]),
        status=str(row["status"]),
        summary=None if row["summary"] is None else str(row["summary"]),
    )


__all__ = ("InterfaceElfieRecord", "InterfaceQueryRepository", "InterfaceUserRecord")
