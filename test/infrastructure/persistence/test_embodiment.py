"""SQLite persistence for serialized embodiment transitions."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.infrastructure.persistence.store import get_db, init_db
from app.orchestration.embodiment.models import EmbodimentSession
from app.orchestration.embodiment.ports import EmbodimentLeaseConflict
from infrastructure.persistence.bodies import SQLiteBodiesAdapter
from infrastructure.persistence.embodiment import (
    abort_hosting,
    begin_hosting,
    complete_hosting,
    complete_return,
    expire_stale_lease,
    get_embodiment_session,
    list_embodiment_sessions,
    recover_offline_session,
    renew_hosting_heartbeat,
    start_return,
)
from nest.embodiment import EmbodimentState


def test_embodiment_session_persists_one_hosted_lease_at_a_time(tmp_path: Path) -> None:
    db_path = _final_elfie_database(tmp_path)
    first = _enroll(db_path, "身体一")
    second = _enroll(db_path, "身体二")

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


def test_list_sessions_projects_missing_rows_as_at_nest_without_writing(
    tmp_path: Path,
) -> None:
    db_path = _final_elfie_database(tmp_path)

    sessions = list_embodiment_sessions(db_path)

    assert sessions == (
        EmbodimentSession(
            elfie_id="00000001",
            state=EmbodimentState.AT_NEST,
            body_id=None,
            lease_expires_at=None,
            lease_version=0,
        ),
    )
    with get_db(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM embodiment_sessions").fetchone()[0] == 0


def test_aborting_a_failed_hosting_releases_the_lease_and_returns_to_nest(
    tmp_path: Path,
) -> None:
    # Given: a body lease was acquired before the connection attempt fails.
    db_path = _final_elfie_database(tmp_path)
    body = _enroll(db_path, "身体一")
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
    body = _enroll(db_path, "身体一")
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
            "INSERT INTO users(id, account_id, password_hash, role) VALUES (1, ?, ?, ?)",
            ("owner", "hash", "owner"),
        )
        connection.execute(
            """INSERT INTO elfies(
                   elfie_id, name, owner_user_id, species, adopted_at, status
               ) VALUES ('00000001', '测试精灵', 1, 'test', CURRENT_TIMESTAMP, 'offline')"""
        )
        connection.commit()
    return db_path


def _enroll(db_path: str, display_name: str):
    return SQLiteBodiesAdapter(db_path).enroll(
        owner_user_id=1,
        elfie_id="00000001",
        display_name=display_name,
        body_type="toy",
    )
