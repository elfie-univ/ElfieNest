"""Final-root integration coverage for Elfie, Nest, food, body, and leases."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.features.adoption.service import AdoptionRequest, adopt_elfie_for_user
from app.infrastructure.devices.registry import DeviceCredentialError, DeviceRegistry
from app.infrastructure.persistence.elfie_repository import ElfieRepository
from app.infrastructure.persistence.embodiment_sessions import (
    EmbodimentLeaseConflict,
    begin_hosting,
    complete_hosting,
    complete_return,
    get_embodiment_session,
    start_return,
)
from app.infrastructure.persistence.final_schema import create_final_nest_database
from app.infrastructure.persistence.food_assignments import set_elfie_main_food_id
from app.infrastructure.persistence.nest_repository import SQLiteNestRepository
from app.infrastructure.persistence.nest_state_repository import (
    SQLiteNestStateRepository,
)
from app.infrastructure.persistence.store import get_db
from nest.embodiment import EmbodimentState
from nest.state.models import PersistentResidentState, ResidentPresence, WorldCatalog

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
               VALUES ('local', 4, 1.0)"""
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


def test_elfie_repository_persists_owner_profile_main_food_and_nullable_bed(
    tmp_path: Path,
) -> None:
    # Given: an exact final root database and its Owner.
    db_path = _final_database(tmp_path)
    repository = ElfieRepository(db_path)

    # When: one final Elfie is adopted and its profile/main-food fields are updated.
    repository.reserve_adoption(
        elfie_id="00000001",
        owner_user_id=1,
        name="小狐",
        species="fox",
        summary="好奇探索",
        max_elfies=2,
    )
    repository.update_profile(
        "00000001", gender="female", birth_date="2026-07-30", summary="爱探索"
    )
    set_elfie_main_food_id(db_path, "00000001", "local-main")

    # Then: the final row is owner-scoped, complete, and no legacy table appeared.
    record = repository.get_for_owner("00000001", owner_user_id=1)
    assert record is not None
    assert record.elfie_id == "00000001"
    assert record.owner_user_id == 1
    assert record.gender == "female"
    assert record.summary == "爱探索"
    assert record.main_food_id == "local-main"
    assert record.bed_number is None
    assert repository.list_for_owner(1) == [record]
    _assert_only_final_tables(db_path)


def test_adoption_service_creates_an_eight_digit_final_elfie_without_sql(
    tmp_path: Path,
) -> None:
    # Given: a final Owner database and a deterministic successful generator.
    db_path = _final_database(tmp_path)
    request = AdoptionRequest(
        name="小狐",
        species_id="fox",
        personality_style="好奇探索",
        height="standard",
        build="standard",
    )

    # When: the adoption feature completes through its repository boundary.
    with patch(
        "app.features.adoption.service.ElfieGenerator.generate_for_species",
        return_value=None,
    ):
        result = adopt_elfie_for_user(db_path, user_id=1, request=request)

    # Then: ownership/profile are final, ID is exactly eight digits, and no SQL leaked.
    assert len(result.elfie_id) == 8
    assert result.elfie_id.isdigit()
    record = ElfieRepository(db_path).get_for_owner(result.elfie_id, owner_user_id=1)
    assert record is not None
    assert record.summary == "好奇探索"
    source = Path("app/features/adoption/service.py").read_text(encoding="utf-8")
    assert "connection.execute(" not in source
    assert "elfie_registry" not in source
    _assert_only_final_tables(db_path)


def test_nest_repositories_store_only_settings_presence_and_bed_number(
    tmp_path: Path,
) -> None:
    # Given: a final Elfie and a Runtime catalog containing geometry-owned labels.
    db_path = _final_database(tmp_path)
    ElfieRepository(db_path).reserve_adoption(
        elfie_id="00000001",
        owner_user_id=1,
        name="小狐",
        species="fox",
        summary=None,
        max_elfies=2,
    )
    catalog = WorldCatalog(nest_id="local-nest", revision=7, zones=())
    state_repository = SQLiteNestStateRepository(db_path)

    # When: Runtime revision/resident presence and a nullable bed are persisted.
    state_repository.save_catalog(catalog)
    state_repository.save_resident(
        PersistentResidentState(elfie_id="00000001", presence=ResidentPresence.AWAY)
    )
    with get_db(db_path) as connection:
        nest_repository = SQLiteNestRepository(connection)
        nest_repository.assign_bed(elfie_id="00000001", bed_number=4)
        connection.commit()

    # Then: reopening restores semantic state without storing a Godot catalog.
    restored = SQLiteNestStateRepository(db_path).load_snapshot()
    assert restored.catalog is None
    assert restored.desired_bed_count == 4
    assert restored.residents == (
        PersistentResidentState(elfie_id="00000001", presence=ResidentPresence.AWAY),
    )
    assert ElfieRepository(db_path).get("00000001").bed_number == 4
    with get_db(db_path) as connection:
        bed = SQLiteNestRepository(connection).load_view().beds[3]
    assert bed["occupant_owner_user_id"] == 1
    assert bed["occupant_owner_account_id"] == "owner"
    assert bed["occupant_owner_display_name"] == "Owner Name"
    with pytest.raises(ValueError):
        with get_db(db_path) as connection:
            SQLiteNestRepository(connection).assign_bed(
                elfie_id="00000001", bed_number=5
            )
    _assert_only_final_tables(db_path)


def test_body_secret_revoke_audit_and_versioned_lease_reject_stale_writes(
    tmp_path: Path,
) -> None:
    # Given: a final Elfie and one explicitly owned external body.
    db_path = _final_database(tmp_path)
    ElfieRepository(db_path).reserve_adoption(
        elfie_id="00000001",
        owner_user_id=1,
        name="小狐",
        species="fox",
        summary=None,
        max_elfies=2,
    )
    registry = DeviceRegistry(db_path)
    credential = registry.enroll(
        owner_elfie_id="00000001", display_name="客厅玩具", body_type="toy"
    )
    assert registry.authenticate(credential.bearer_token).owner_elfie_id == "00000001"

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

    registry.revoke("00000001", credential.body_id)
    with pytest.raises(DeviceCredentialError):
        registry.authenticate(credential.bearer_token)
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
