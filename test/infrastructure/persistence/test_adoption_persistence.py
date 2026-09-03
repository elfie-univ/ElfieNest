from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.features.adoption import (
    AdoptionPortCapacityReached,
    AdoptionPortNestCapacityReached,
)
from app.orchestration.resident_admission import (
    AdmissionPublication,
    AdmissionReservation,
    idempotency_key_digest,
)
from infrastructure.persistence.adoption import SQLiteAdoptionAdapter
from infrastructure.persistence.nest_db.store import get_db, init_db


def _reservation(elfie_id: str, owner_user_id: int) -> AdmissionReservation:
    key = f"submit:{elfie_id}"
    return AdmissionReservation(
        admission_id=f"admission:{elfie_id}",
        idempotency_key_digest=idempotency_key_digest(key),
        elfie_id=elfie_id,
        owner_user_id=owner_user_id,
        candidate_set_id=f"set:{elfie_id}",
        candidate_id=f"candidate:{elfie_id}",
        display_name=elfie_id,
        species_id="fox",
        gender="female",
        age_years=2,
        adoption_anchor_at="2000-01-01T00:00:00+00:00",
    )


def _configure_nest(connection, *, bed_count: int = 4) -> None:
    connection.execute(
        """INSERT INTO nest_settings(nest_id,bed_count,tick_interval_sec)
           VALUES ('local-nest',?,0.5)""",
        (bed_count,),
    )
    connection.commit()


def _owner(db_path: str, account_id: str, *, limit: int) -> int:
    with get_db(db_path) as connection:
        user_id = int(
            connection.execute(
                """INSERT INTO users(account_id,password_hash,role,elfie_limit)
                   VALUES (?,?, 'user',?)""",
                (account_id, "unused", limit),
            ).lastrowid
        )
        connection.commit()
        return user_id


def test_reserve_uses_the_member_override_in_one_write_transaction(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        _configure_nest(connection)
    owner_user_id = _owner(db_path, "alice", limit=1)
    adapter = SQLiteAdoptionAdapter(db_path)

    first = adapter.reserve(_reservation("00000001", owner_user_id), default_limit=3)

    with pytest.raises(AdoptionPortCapacityReached) as raised:
        adapter.reserve(_reservation("00000002", owner_user_id), default_limit=3)
    assert raised.value.limit == 1
    assert first.state == "reserved"
    quota = adapter.get_quota(owner_user_id, 3)
    assert quota is not None
    assert quota.used == 1


def test_duplicate_reservation_returns_the_durable_record_and_abort_releases_capacity(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        _configure_nest(connection)
    owner_user_id = _owner(db_path, "alice", limit=1)
    adapter = SQLiteAdoptionAdapter(db_path)
    reservation = _reservation("00000001", owner_user_id)

    first = adapter.reserve(reservation, default_limit=3)
    repeated = adapter.reserve(reservation, default_limit=3)
    assert repeated == first
    adapter.abort(first.admission_id, error_code="test_failure")
    quota = adapter.get_quota(owner_user_id, 3)
    assert quota is not None and quota.used == 0


def test_concurrent_reservations_cannot_exceed_quota(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        _configure_nest(connection)
    owner_user_id = _owner(db_path, "alice", limit=1)
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


def test_global_nest_capacity_applies_across_different_members(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        _configure_nest(connection, bed_count=4)
    owners = tuple(_owner(db_path, f"user-{index}", limit=4) for index in range(5))
    adapter = SQLiteAdoptionAdapter(db_path)
    for index, owner_user_id in enumerate(owners[:4], start=1):
        adapter.reserve(_reservation(f"{index:08d}", owner_user_id), default_limit=4)

    capacity = adapter.get_nest_capacity()
    assert capacity.used == 4
    assert capacity.maximum == 4
    with pytest.raises(AdoptionPortNestCapacityReached) as raised:
        adapter.reserve(_reservation("00000005", owners[4]), default_limit=4)
    assert raised.value.limit == 4


def test_publication_state_machine_commits_only_after_publishing(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        _configure_nest(connection)
    owner_user_id = _owner(db_path, "alice", limit=3)
    adapter = SQLiteAdoptionAdapter(db_path)
    reservation = _reservation("00000001", owner_user_id)
    record = adapter.reserve(reservation, default_limit=3)
    record = adapter.transition(record.admission_id, "reserved", "compiling")
    record = adapter.transition(
        record.admission_id,
        "compiling",
        "staged",
        manifest_id="manifest-1",
        content_hash="a" * 64,
        output_ids_hash="b" * 64,
        compiler_version="compiler-1",
        schema_version=1,
    )
    record = adapter.transition(record.admission_id, "staged", "publishing")
    publication = AdmissionPublication(
        manifest_id="manifest-1",
        content_hash="a" * 64,
        output_ids_hash="b" * 64,
        compiler_version="compiler-1",
        schema_version=1,
        adopted_at=record.created_at,
    )
    committed = adapter.commit(record.admission_id, publication)
    assert committed.state == "committed"
    current = adapter.get(record.admission_id)
    assert current is not None and current.runtime_status == "offline"
    with get_db(db_path) as connection:
        row = connection.execute(
            "SELECT owner_user_id, adopted_at, status FROM elfies WHERE elfie_id=?",
            (reservation.elfie_id,),
        ).fetchone()
    assert row is not None
    assert int(row["owner_user_id"]) == owner_user_id
    assert row["adopted_at"] == publication.adopted_at
    assert row["status"] == "offline"
