"""Root lease adapter behavior beyond the cross-domain smoke scenario."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.features.bodies.ports import BodiesPortConflict
from infrastructure.persistence.elfie_workspace.bodies import SQLiteBodiesAdapter
from infrastructure.persistence.elfie_workspace.embodiment import (
    begin_hosting,
    complete_hosting,
    complete_return,
    start_return,
)
from infrastructure.persistence.nest_db.final_schema import create_final_nest_database
from infrastructure.persistence.nest_db.store import get_db
from test.app.interfaces.api._helpers import adopt_test_elfie


def _reserve_elfie(db_path: str) -> None:
    adopt_test_elfie(db_path, 1, elfie_id="00000001", name="小狐")


def test_returned_elfie_can_host_again_with_next_lease_version(tmp_path: Path) -> None:
    # Given: one final Elfie and two enrolled external bodies.
    db_path = str(create_final_nest_database(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        connection.execute(
            """INSERT INTO users(id, account_id, role, password_hash)
               VALUES (1, 'owner', 'owner', 'hash')"""
        )
        connection.commit()
    _reserve_elfie(db_path)
    registry = SQLiteBodiesAdapter(db_path)
    first_body = registry.enroll(
        owner_user_id=1,
        elfie_id="00000001",
        display_name="客厅身体",
        body_type="toy",
    )
    second_body = registry.enroll(
        owner_user_id=1,
        elfie_id="00000001",
        display_name="书房身体",
        body_type="toy",
    )

    # When: the first lease completes and a second hosting starts.
    switching = begin_hosting(db_path, "00000001", first_body.body_id, lease_seconds=30)
    hosted = complete_hosting(db_path, "00000001", switching.lease_version)
    returning = start_return(db_path, "00000001", hosted.lease_version)
    returned = complete_return(db_path, "00000001", returning.lease_version)
    second = begin_hosting(db_path, "00000001", second_body.body_id, lease_seconds=30)

    # Then: the monotonic version continues and body availability follows the lease.
    assert second.lease_version == returned.lease_version + 1
    with get_db(db_path) as connection:
        statuses = {
            str(row["body_id"]): str(row["status"])
            for row in connection.execute(
                "SELECT body_id, status FROM external_bodies"
            ).fetchall()
        }
        elfie_status = str(
            connection.execute(
                "SELECT status FROM elfies WHERE elfie_id='00000001'"
            ).fetchone()["status"]
        )
    assert statuses == {
        first_body.body_id: "available",
        second_body.body_id: "active",
    }
    assert elfie_status == "away"


def test_active_body_cannot_be_revoked(tmp_path: Path) -> None:
    # Given: one final Elfie currently holds an external body lease.
    db_path = str(create_final_nest_database(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        connection.execute(
            """INSERT INTO users(id, account_id, role, password_hash)
               VALUES (1, 'owner', 'owner', 'hash')"""
        )
        connection.commit()
    _reserve_elfie(db_path)
    registry = SQLiteBodiesAdapter(db_path)
    body = registry.enroll(
        owner_user_id=1,
        elfie_id="00000001",
        display_name="客厅身体",
        body_type="toy",
    )
    begin_hosting(db_path, "00000001", body.body_id, lease_seconds=30)

    # When/Then: the schema conflict is exposed as the registry's domain error.
    with pytest.raises(BodiesPortConflict):
        registry.revoke(
            owner_user_id=1,
            elfie_id="00000001",
            body_id=body.body_id,
        )
