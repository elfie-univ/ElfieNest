"""SQLite implementation of the Adoption ownership Port."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from app.features.adoption import (
    AdoptionNestCapacityRecord,
    AdoptionPortCapacityReached,
    AdoptionPortError,
    AdoptionPortNestCapacityReached,
    AdoptionPortOwnerNotFound,
    AdoptionQuotaRecord,
    AdoptionReservationRecord,
)
from infrastructure.persistence.nest_db.sqlite_connection import app_sqlite_connection
from nest.public import NestConfig


class SQLiteAdoptionAdapter:
    """Own the one atomic quota check and ownership write path."""

    def __init__(self, db_path: str, *, nest_config: NestConfig | None = None) -> None:
        self._db_path = db_path
        self._nest_config = nest_config or NestConfig()

    def get_quota(
        self,
        owner_user_id: int,
        default_limit: int,
    ) -> AdoptionQuotaRecord | None:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                owner = connection.execute(
                    "SELECT elfie_limit FROM users WHERE id=?",
                    (owner_user_id,),
                ).fetchone()
                if owner is None:
                    return None
                used = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM elfies WHERE owner_user_id=?",
                        (owner_user_id,),
                    ).fetchone()[0]
                )
        except sqlite3.Error as error:
            raise AdoptionPortError("unable to read Adoption quota") from error
        effective_limit = default_limit if owner[0] is None else int(owner[0])
        return AdoptionQuotaRecord(used=used, effective_limit=effective_limit)

    def get_nest_capacity(self) -> AdoptionNestCapacityRecord:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                row = connection.execute(
                    "SELECT bed_count FROM nest_settings WHERE nest_id='local-nest'"
                ).fetchone()
                used = int(
                    connection.execute("SELECT COUNT(*) FROM elfies").fetchone()[0]
                )
        except AdoptionPortError:
            raise
        except sqlite3.Error as error:
            raise AdoptionPortError("unable to read Nest capacity") from error
        maximum = self._nest_config.bed_count if row is None else int(row[0])
        return AdoptionNestCapacityRecord(used=used, maximum=maximum)

    def reserve(
        self,
        reservation: AdoptionReservationRecord,
        default_limit: int,
    ) -> None:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                owner = connection.execute(
                    "SELECT elfie_limit FROM users WHERE id=?",
                    (reservation.owner_user_id,),
                ).fetchone()
                if owner is None:
                    raise AdoptionPortOwnerNotFound
                nest = connection.execute(
                    "SELECT bed_count FROM nest_settings WHERE nest_id='local-nest'"
                ).fetchone()
                nest_limit = (
                    self._nest_config.bed_count if nest is None else int(nest[0])
                )
                nest_used = int(
                    connection.execute("SELECT COUNT(*) FROM elfies").fetchone()[0]
                )
                if nest_used >= nest_limit:
                    raise AdoptionPortNestCapacityReached(nest_limit)
                effective_limit = default_limit if owner[0] is None else int(owner[0])
                used = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM elfies WHERE owner_user_id=?",
                        (reservation.owner_user_id,),
                    ).fetchone()[0]
                )
                if used >= effective_limit:
                    raise AdoptionPortCapacityReached(effective_limit)
                connection.execute(
                    """INSERT INTO elfies(
                           elfie_id, name, original_name, owner_user_id, species, gender,
                           birth_date, adopted_at, home_anchor_id, status, summary
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 'offline', ?)""",
                    (
                        reservation.elfie_id,
                        reservation.name,
                        reservation.original_name,
                        reservation.owner_user_id,
                        reservation.species_id,
                        reservation.gender,
                        reservation.birth_date,
                        datetime.now(timezone.utc).isoformat(),
                        reservation.summary,
                    ),
                )
                connection.commit()
        except (
            AdoptionPortCapacityReached,
            AdoptionPortNestCapacityReached,
            AdoptionPortOwnerNotFound,
            AdoptionPortError,
        ):
            raise
        except sqlite3.Error as error:
            raise AdoptionPortError("unable to reserve Adoption ownership") from error

    def release(self, elfie_id: str) -> None:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("DELETE FROM elfies WHERE elfie_id=?", (elfie_id,))
                connection.commit()
        except sqlite3.Error as error:
            raise AdoptionPortError("unable to release Adoption ownership") from error


__all__ = ("SQLiteAdoptionAdapter",)
