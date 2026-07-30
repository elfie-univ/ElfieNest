"""SQLite persistence for serialized embodiment transitions."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.infrastructure.devices import DeviceRegistry
from app.infrastructure.persistence.embodiment_sessions import (
    EmbodimentLeaseConflict,
    abort_hosting,
    begin_hosting,
    complete_hosting,
    complete_return,
    expire_stale_lease,
    get_embodiment_session,
    recover_offline_session,
    renew_hosting_heartbeat,
    start_return,
)
from app.infrastructure.persistence.store import get_db, init_db
from nest.embodiment import EmbodimentState


def test_embodiment_session_persists_one_hosted_lease_at_a_time(tmp_path: Path) -> None:
    db_path = _final_elfie_database(tmp_path)
    registry = DeviceRegistry(db_path)
    first = registry.enroll("00000001", "身体一", "toy")
    second = registry.enroll("00000001", "身体二", "toy")

    switching = begin_hosting(db_path, "00000001", first.body_id, lease_seconds=30)

    assert switching.state is EmbodimentState.SWITCHING_TO_HOSTED
    with pytest.raises(EmbodimentLeaseConflict):
        begin_hosting(db_path, "00000001", second.body_id, lease_seconds=30)
    hosted = complete_hosting(db_path, "00000001", switching.lease_version)
    returning = start_return(db_path, "00000001", hosted.lease_version)
    at_nest = complete_return(db_path, "00000001", returning.lease_version)

    assert at_nest.state is EmbodimentState.AT_NEST
    assert at_nest.body_id is None
    assert get_embodiment_session(db_path, "00000001").state is EmbodimentState.AT_NEST


def test_aborting_a_failed_hosting_releases_the_lease_and_returns_to_nest(
    tmp_path: Path,
) -> None:
    # Given: a body lease was acquired before the connection attempt fails.
    db_path = _final_elfie_database(tmp_path)
    body = DeviceRegistry(db_path).enroll("00000001", "身体一", "toy")
    switching = begin_hosting(db_path, "00000001", body.body_id, lease_seconds=30)

    # When: orchestration aborts that failed connection attempt.
    restored = abort_hosting(db_path, "00000001", switching.lease_version)

    # Then: no body id or lease survives the rollback.
    assert restored.state is EmbodimentState.AT_NEST
    assert restored.body_id is None
    assert restored.lease_expires_at is None


def test_stale_hosting_lease_becomes_offline_and_cannot_be_renewed(
    tmp_path: Path,
) -> None:
    # Given: a hosted body has a lease that has already expired.
    db_path = _final_elfie_database(tmp_path)
    body = DeviceRegistry(db_path).enroll("00000001", "身体一", "toy")
    switching = begin_hosting(db_path, "00000001", body.body_id, lease_seconds=30)
    hosted = complete_hosting(db_path, "00000001", switching.lease_version)

    # When: the heartbeat watchdog observes time after the lease deadline.
    offline = expire_stale_lease(
        db_path,
        "00000001",
        now=(hosted.lease_expires_at or 0) + 1,
    )

    # Then: the persisted state is offline and the released body has no active lease.
    assert offline.state is EmbodimentState.OFFLINE
    assert offline.body_id is None
    assert offline.lease_expires_at is None
    with pytest.raises(EmbodimentLeaseConflict):
        renew_hosting_heartbeat(
            db_path, "00000001", hosted.lease_version, lease_seconds=30
        )

    recovered = recover_offline_session(db_path, "00000001", offline.lease_version)

    assert recovered.state is EmbodimentState.AT_NEST
    assert recovered.body_id is None
    assert recovered.lease_expires_at is None


def _final_elfie_database(tmp_path: Path) -> str:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT INTO users(id, username, password_hash, role) VALUES (1, ?, ?, ?)",
            ("owner", "hash", "owner"),
        )
        connection.execute(
            """INSERT INTO elfies(
                   elfie_id, name, owner_user_id, species, adopted_at, status
               ) VALUES ('00000001', '测试精灵', 1, 'test', CURRENT_TIMESTAMP, 'offline')"""
        )
        connection.commit()
    return db_path
