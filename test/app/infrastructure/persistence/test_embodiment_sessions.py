"""SQLite persistence for serialized embodiment transitions."""

from __future__ import annotations

from pathlib import Path

import pytest

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
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT INTO elfie_registry (elfie_id, name) VALUES (?, ?)",
            ("elfie-1", "测试精灵"),
        )
        connection.commit()

    switching = begin_hosting(db_path, "elfie-1", "toy-1", lease_seconds=30)

    assert switching.state is EmbodimentState.SWITCHING_TO_HOSTED
    with pytest.raises(EmbodimentLeaseConflict):
        begin_hosting(db_path, "elfie-1", "toy-2", lease_seconds=30)
    hosted = complete_hosting(db_path, "elfie-1", switching.session_id)
    returning = start_return(db_path, "elfie-1", hosted.session_id)
    at_nest = complete_return(db_path, "elfie-1", returning.session_id)

    assert at_nest.state is EmbodimentState.AT_NEST
    assert at_nest.body_id is None
    assert get_embodiment_session(db_path, "elfie-1").state is EmbodimentState.AT_NEST


def test_aborting_a_failed_hosting_releases_the_lease_and_returns_to_nest(
    tmp_path: Path,
) -> None:
    # Given: a body lease was acquired before the connection attempt fails.
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT INTO elfie_registry (elfie_id, name) VALUES (?, ?)",
            ("elfie-1", "测试精灵"),
        )
        connection.commit()
    switching = begin_hosting(db_path, "elfie-1", "toy-1", lease_seconds=30)

    # When: orchestration aborts that failed connection attempt.
    restored = abort_hosting(db_path, "elfie-1", switching.session_id)

    # Then: no body id or lease survives the rollback.
    assert restored.state is EmbodimentState.AT_NEST
    assert restored.body_id is None
    assert restored.lease_expires_at is None


def test_stale_hosting_lease_becomes_offline_and_cannot_be_renewed(
    tmp_path: Path,
) -> None:
    # Given: a hosted body has a lease that has already expired.
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT INTO elfie_registry (elfie_id, name) VALUES (?, ?)",
            ("elfie-1", "测试精灵"),
        )
        connection.commit()
    switching = begin_hosting(db_path, "elfie-1", "toy-1", lease_seconds=30)
    hosted = complete_hosting(db_path, "elfie-1", switching.session_id)

    # When: the heartbeat watchdog observes time after the lease deadline.
    offline = expire_stale_lease(
        db_path,
        "elfie-1",
        now=(hosted.lease_expires_at or 0) + 1,
    )

    # Then: the persisted state is offline and the released body has no active lease.
    assert offline.state is EmbodimentState.OFFLINE
    assert offline.body_id is None
    assert offline.lease_expires_at is None
    with pytest.raises(EmbodimentLeaseConflict):
        renew_hosting_heartbeat(db_path, "elfie-1", hosted.session_id, lease_seconds=30)

    recovered = recover_offline_session(db_path, "elfie-1", hosted.session_id)

    assert recovered.state is EmbodimentState.AT_NEST
    assert recovered.body_id is None
    assert recovered.lease_expires_at is None
