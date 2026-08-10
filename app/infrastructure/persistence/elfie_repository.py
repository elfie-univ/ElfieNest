"""Persistence boundary for final Elfie ownership, profile, and main food."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from infrastructure.persistence.store import get_db


@dataclass(frozen=True)
class ElfieRecord:
    """One final ``elfies`` row exposed without SQLite details."""

    __slots__ = (
        "elfie_id",
        "name",
        "owner_user_id",
        "species",
        "gender",
        "birth_date",
        "bed_number",
        "status",
        "summary",
        "main_food_id",
    )

    elfie_id: str
    name: str
    owner_user_id: int
    species: str
    gender: str | None
    birth_date: str | None
    bed_number: int | None
    status: str
    summary: str | None
    main_food_id: str | None


@dataclass(frozen=True)
class ElfieCapacityExceeded(RuntimeError):
    """The Owner has no remaining final Elfie capacity."""

    __slots__ = ("owner_user_id", "limit")

    owner_user_id: int
    limit: int

    def __str__(self) -> str:
        return f"owner {self.owner_user_id} already has {self.limit} Elfies"


@dataclass(frozen=True)
class ElfieOwnerNotFound(RuntimeError):
    """The requested final Owner row does not exist."""

    __slots__ = ("owner_user_id",)

    owner_user_id: int

    def __str__(self) -> str:
        return f"owner {self.owner_user_id} not found"


class ElfieRepositoryWriteError(RuntimeError):
    """A final Elfie write completed without a readable record."""


class ElfieRepository:
    """Own all application reads and writes for the final ``elfies`` table."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def reserve_adoption(
        self,
        *,
        elfie_id: str,
        owner_user_id: int,
        name: str,
        species: str,
        summary: str | None,
        max_elfies: int,
    ) -> ElfieRecord:
        """Atomically enforce Owner capacity and insert one final Elfie."""
        with get_db(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            owner = connection.execute(
                "SELECT elfie_limit FROM users WHERE id=?", (owner_user_id,)
            ).fetchone()
            if owner is None:
                raise ElfieOwnerNotFound(owner_user_id)
            effective_limit = max_elfies if owner[0] is None else int(owner[0])
            current_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM elfies WHERE owner_user_id=?",
                    (owner_user_id,),
                ).fetchone()[0]
            )
            if current_count >= effective_limit:
                raise ElfieCapacityExceeded(owner_user_id, effective_limit)
            adopted_at = datetime.now(timezone.utc).isoformat()
            connection.execute(
                """INSERT INTO elfies(
                       elfie_id, name, owner_user_id, species, adopted_at,
                       bed_number, status, summary
                   ) VALUES (?, ?, ?, ?, ?, NULL, 'offline', ?)""",
                (elfie_id, name, owner_user_id, species, adopted_at, summary),
            )
            connection.commit()
        record = self.get(elfie_id)
        if record is None:
            raise ElfieRepositoryWriteError("inserted Elfie could not be reloaded")
        return record

    def delete(self, elfie_id: str) -> None:
        """Release a failed adoption reservation without touching its workspace."""
        with get_db(self._db_path) as connection:
            connection.execute("DELETE FROM elfies WHERE elfie_id=?", (elfie_id,))
            connection.commit()

    def update_profile(
        self,
        elfie_id: str,
        *,
        gender: str | None,
        birth_date: str | None,
        summary: str | None,
    ) -> None:
        """Persist final public profile columns for one Elfie."""
        with get_db(self._db_path) as connection:
            connection.execute(
                """UPDATE elfies
                   SET gender=?, birth_date=?, summary=?, updated_at=CURRENT_TIMESTAMP
                   WHERE elfie_id=?""",
                (gender, birth_date, summary, elfie_id),
            )
            connection.commit()

    def count_for_owner(self, owner_user_id: int) -> int:
        """Count final Elfies owned by one user."""
        with get_db(self._db_path) as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM elfies WHERE owner_user_id=?",
                    (owner_user_id,),
                ).fetchone()[0]
            )

    def count_all(self) -> int:
        """Count every final Elfie registered in this Nest."""
        with get_db(self._db_path) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM elfies").fetchone()[0])

    def list_all(self) -> list[ElfieRecord]:
        """List every final Elfie for Runtime bootstrap."""
        with get_db(self._db_path) as connection:
            rows = connection.execute(
                "SELECT * FROM elfies ORDER BY adopted_at, elfie_id"
            ).fetchall()
        return [_record(row) for row in rows]

    def get(self, elfie_id: str) -> ElfieRecord | None:
        """Load one final Elfie by its stable eight-digit ID."""
        with get_db(self._db_path) as connection:
            row = connection.execute(
                "SELECT * FROM elfies WHERE elfie_id=?", (elfie_id,)
            ).fetchone()
        return None if row is None else _record(row)

    def get_for_owner(self, elfie_id: str, *, owner_user_id: int) -> ElfieRecord | None:
        """Load one final Elfie only when ownership matches."""
        with get_db(self._db_path) as connection:
            row = connection.execute(
                "SELECT * FROM elfies WHERE elfie_id=? AND owner_user_id=?",
                (elfie_id, owner_user_id),
            ).fetchone()
        return None if row is None else _record(row)

    def list_for_owner(self, owner_user_id: int) -> list[ElfieRecord]:
        """List final Elfies for one Owner in stable adoption order."""
        with get_db(self._db_path) as connection:
            rows = connection.execute(
                """SELECT * FROM elfies WHERE owner_user_id=?
                   ORDER BY adopted_at, elfie_id""",
                (owner_user_id,),
            ).fetchall()
        return [_record(row) for row in rows]


def _record(row: sqlite3.Row) -> ElfieRecord:
    return ElfieRecord(
        elfie_id=str(row["elfie_id"]),
        name=str(row["name"]),
        owner_user_id=int(row["owner_user_id"]),
        species=str(row["species"]),
        gender=None if row["gender"] is None else str(row["gender"]),
        birth_date=None if row["birth_date"] is None else str(row["birth_date"]),
        bed_number=None if row["bed_number"] is None else int(row["bed_number"]),
        status=str(row["status"]),
        summary=None if row["summary"] is None else str(row["summary"]),
        main_food_id=(
            None if row["main_food_id"] is None else str(row["main_food_id"])
        ),
    )


__all__ = (
    "ElfieCapacityExceeded",
    "ElfieOwnerNotFound",
    "ElfieRecord",
    "ElfieRepository",
    "ElfieRepositoryWriteError",
)
