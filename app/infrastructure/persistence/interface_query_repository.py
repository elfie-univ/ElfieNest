"""Final persistence projections used by HTTP interface adapters."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from infrastructure.persistence.store import get_db


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


_ELFIE_SELECT = """
SELECT elfies.elfie_id,elfies.name,elfies.owner_user_id,
       users.account_id AS owner_account_id,
       users.display_name AS owner_display_name,
       elfies.species,elfies.gender,elfies.birth_date,elfies.adopted_at,
       elfies.bed_number,elfies.status,elfies.summary
FROM elfies JOIN users ON users.id=elfies.owner_user_id
"""


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
)
