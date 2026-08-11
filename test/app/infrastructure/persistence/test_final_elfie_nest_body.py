"""Final-root integration coverage for Elfie, Nest, food, body, and leases."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.features.adoption import AdoptionReservationRecord
from app.features.bodies.ports import (
    BodiesPortCredentialRejected,
)
from app.features.nest_management import NestPortBedNotFound
from app.orchestration.embodiment.ports import EmbodimentLeaseConflict
from infrastructure.persistence.adoption import SQLiteAdoptionAdapter
from infrastructure.persistence.elfie_workspace.bodies import SQLiteBodiesAdapter
from infrastructure.persistence.elfie_workspace.elfies import (
    SQLiteElfiesProjectionAdapter,
)
from infrastructure.persistence.elfie_workspace.embodiment import (
    begin_hosting,
    complete_hosting,
    complete_return,
    get_embodiment_session,
    start_return,
)
from infrastructure.persistence.food import SQLiteFoodAdapter
from infrastructure.persistence.nest_db.final_schema import create_final_nest_database
from infrastructure.persistence.nest_db.nest_management import (
    SQLiteNestManagementAdapter,
)
from infrastructure.persistence.nest_db.nest_state import SQLiteNestStateAdapter
from infrastructure.persistence.nest_db.store import get_db
from nest.embodiment import EmbodimentState
from nest.state.models import PersistentResidentState, ResidentPresence, WorldCatalog
from test.app.interfaces.api._helpers import adopt_test_elfie

FINAL_TABLES = {
    "device_audit_events",
    "elfies",
    "embodiment_sessions",
    "external_bodies",
    "food_packages",
    "local_installations",
    "nest_settings",
    "sessions",
    "users",
}


def _final_database(tmp_path: Path) -> str:
    db_path = str(create_final_nest_database(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        connection.execute(
            """INSERT INTO users
               (id, account_id, display_name, role, password_hash, elfie_limit)
               VALUES (1, 'owner', 'Owner Name', 'owner', 'hash', 2)"""
        )
        connection.execute(
            """INSERT INTO nest_settings(nest_id, bed_count, tick_interval_sec)
               VALUES ('local-nest', 4, 1.0)"""
        )
        connection.commit()
    return db_path


def _assert_only_final_tables(db_path: str) -> None:
    with get_db(db_path) as connection:
        tables = {
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert tables == FINAL_TABLES


def _reserve_elfie(
    db_path: str,
    *,
    elfie_id: str = "00000001",
    summary: str = "好奇探索",
) -> None:
    SQLiteAdoptionAdapter(db_path).reserve(
        AdoptionReservationRecord(
            elfie_id=elfie_id,
            owner_user_id=1,
            name="小狐",
            species_id="fox",
            gender="female",
            birth_date="2026-07-30",
            summary=summary,
        ),
        default_limit=2,
    )


def test_final_adapters_persist_owner_profile_main_food_and_nullable_bed(
    tmp_path: Path,
) -> None:
    # Given: an exact final root database and its Owner.
    db_path = _final_database(tmp_path)
    # When: one final Elfie is adopted and its main-food field is updated.
    _reserve_elfie(db_path, summary="爱探索")
    SQLiteFoodAdapter(db_path).set_main_food("00000001", "local-main")

    # Then: the final row is owner-scoped, complete, and no legacy table appeared.
    projection = SQLiteElfiesProjectionAdapter(db_path)
    record = projection.get_directory("00000001")
    assert record is not None
    assert record.elfie_id == "00000001"
    assert record.owner_user_id == 1
    assert record.gender == "female"
    assert record.summary == "爱探索"
    assignment = SQLiteFoodAdapter(db_path).get_assignment("00000001")
    assert assignment is not None
    assert assignment.main_food_id == "local-main"
    assert all(
        bed.occupant_id != "00000001"
        for bed in SQLiteNestManagementAdapter(db_path).load_snapshot().beds
    )
    assert projection.list_directory(owner_user_id=1) == (record,)
    _assert_only_final_tables(db_path)


def test_adoption_service_creates_an_eight_digit_final_elfie_without_sql(
    tmp_path: Path,
) -> None:
    # Given: a final Owner database.
    db_path = _final_database(tmp_path)

    # When: the final Adoption adapters create one Elfie fixture.
    elfie_id = adopt_test_elfie(db_path, 1, name="小狐")

    # Then: ownership/profile are final, ID is exactly eight digits, and no SQL leaked.
    assert len(elfie_id) == 8
    assert elfie_id.isdigit()
    record = SQLiteElfiesProjectionAdapter(db_path).get_directory(elfie_id)
    assert record is not None
    assert record.summary == "好奇探索"
    source = Path("app/features/adoption/facade.py").read_text(encoding="utf-8")
    assert "connection.execute(" not in source
    assert "elfie_registry" not in source
    _assert_only_final_tables(db_path)


def test_nest_repositories_store_only_settings_presence_and_bed_number(
    tmp_path: Path,
) -> None:
    # Given: a final Elfie and a Runtime catalog containing geometry-owned labels.
    db_path = _final_database(tmp_path)
    _reserve_elfie(db_path)
    catalog = WorldCatalog(nest_id="local-nest", revision=7, zones=())
    state_repository = SQLiteNestStateAdapter(db_path)

    # When: Runtime revision/resident presence and a nullable bed are persisted.
    state_repository.save_catalog(catalog)
    state_repository.save_resident(
        PersistentResidentState(elfie_id="00000001", presence=ResidentPresence.AWAY)
    )
    nest_repository = SQLiteNestManagementAdapter(db_path)
    nest_repository.assign_bed("00000001", 4)

    # Then: reopening restores semantic state without storing a Godot catalog.
    restored = SQLiteNestStateAdapter(db_path).load_snapshot()
    assert restored.catalog is None
    assert restored.desired_bed_count == 4
    assert restored.residents == (
        PersistentResidentState(elfie_id="00000001", presence=ResidentPresence.AWAY),
    )
    bed = nest_repository.load_snapshot().beds[3]
    assert bed.occupant_id == "00000001"
    assert bed.occupant_owner_user_id == 1
    assert bed.occupant_owner_account_id == "owner"
    assert bed.occupant_owner_display_name == "Owner Name"
    with pytest.raises(NestPortBedNotFound, match="bed not found"):
        nest_repository.assign_bed("00000001", 5)
    _assert_only_final_tables(db_path)


def test_body_secret_revoke_audit_and_versioned_lease_reject_stale_writes(
    tmp_path: Path,
) -> None:
    # Given: a final Elfie and one explicitly owned external body.
    db_path = _final_database(tmp_path)
    _reserve_elfie(db_path)
    registry = SQLiteBodiesAdapter(db_path)
    credential = registry.enroll(
        owner_user_id=1,
        elfie_id="00000001",
        display_name="客厅玩具",
        body_type="toy",
    )
    bearer_token = f"{credential.body_id}.{credential.secret}"
    assert registry.authenticate(bearer_token).owner_elfie_id == "00000001"

    # When: the body is leased and one writer advances the lease version.
    switching = begin_hosting(db_path, "00000001", credential.body_id, lease_seconds=30)
    hosted = complete_hosting(db_path, "00000001", switching.lease_version)

    # Then: a stale writer is rejected, release permits revoke, and audit is durable.
    with pytest.raises(EmbodimentLeaseConflict):
        complete_hosting(db_path, "00000001", switching.lease_version)
    returning = start_return(db_path, "00000001", hosted.lease_version)
    at_nest = complete_return(db_path, "00000001", returning.lease_version)
    assert at_nest.state is EmbodimentState.AT_NEST
    assert get_embodiment_session(db_path, "00000001").lease_version == 4

    registry.revoke(
        owner_user_id=1,
        elfie_id="00000001",
        body_id=credential.body_id,
    )
    with pytest.raises(BodiesPortCredentialRejected):
        registry.authenticate(bearer_token)
    with get_db(db_path) as connection:
        saved_hash = str(
            connection.execute(
                "SELECT secret_hash FROM external_bodies WHERE body_id=?",
                (credential.body_id,),
            ).fetchone()["secret_hash"]
        )
        events = [
            str(row["event_type"])
            for row in connection.execute(
                "SELECT event_type FROM device_audit_events WHERE body_id=? ORDER BY id",
                (credential.body_id,),
            ).fetchall()
        ]
    assert len(saved_hash) == 64
    assert credential.secret not in saved_hash
    assert events == ["enrolled", "revoked"]
    _assert_only_final_tables(db_path)
