from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.features.adoption import (
    AdoptionPortCapacityReached,
    AdoptionReservationRecord,
)
from app.infrastructure.persistence.store import get_db, init_db
from infrastructure.persistence import SQLiteAdoptionAdapter


def _reservation(elfie_id: str, owner_user_id: int) -> AdoptionReservationRecord:
    return AdoptionReservationRecord(
        elfie_id=elfie_id,
        owner_user_id=owner_user_id,
        name=elfie_id,
        species_id="fox",
        gender="female",
        birth_date="2000-01-01",
        summary="好奇探索",
    )


def test_reserve_uses_the_member_override_in_one_write_transaction(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        owner_user_id = int(
            connection.execute(
                """INSERT INTO users(account_id,password_hash,role,elfie_limit)
                   VALUES ('alice','unused','user',1)"""
            ).lastrowid
        )
        connection.commit()
    adapter = SQLiteAdoptionAdapter(db_path)

    adapter.reserve(_reservation("00000001", owner_user_id), default_limit=3)

    with pytest.raises(AdoptionPortCapacityReached) as raised:
        adapter.reserve(_reservation("00000002", owner_user_id), default_limit=3)
    assert raised.value.limit == 1
    assert adapter.get_quota(owner_user_id, 3) is not None
    assert adapter.get_quota(owner_user_id, 3).used == 1  # type: ignore[union-attr]


def test_concurrent_reservations_cannot_exceed_quota(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        owner_user_id = int(
            connection.execute(
                """INSERT INTO users(account_id,password_hash,role,elfie_limit)
                   VALUES ('alice','unused','user',1)"""
            ).lastrowid
        )
        connection.commit()
    barrier = threading.Barrier(2)

    def reserve(elfie_id: str) -> str:
        barrier.wait(timeout=5)
        try:
            SQLiteAdoptionAdapter(db_path).reserve(
                _reservation(elfie_id, owner_user_id),
                default_limit=3,
            )
        except AdoptionPortCapacityReached:
            return "capacity"
        return "reserved"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(
            future.result(timeout=5)
            for future in (
                executor.submit(reserve, "00000001"),
                executor.submit(reserve, "00000002"),
            )
        )

    assert sorted(outcomes) == ["capacity", "reserved"]
