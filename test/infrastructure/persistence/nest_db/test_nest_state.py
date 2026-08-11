from __future__ import annotations

import pytest

from infrastructure.persistence.nest_db.nest_management import (
    SQLiteNestManagementAdapter,
)
from infrastructure.persistence.nest_db.nest_state import SQLiteNestStateAdapter
from infrastructure.persistence.nest_db.store import get_db, init_db
from nest.state.models import PersistentResidentState, ResidentPresence, WorldCatalog


def _seed_elfie(db_path: str) -> None:
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT INTO users(id, account_id, role, password_hash) "
            "VALUES (1, 'owner', 'owner', 'hash')"
        )
        connection.execute(
            "INSERT INTO nest_settings(nest_id, bed_count, tick_interval_sec) "
            "VALUES ('local-nest', 4, 1.0)"
        )
        connection.execute(
            "INSERT INTO elfies "
            "(elfie_id, name, owner_user_id, species, adopted_at, status) "
            "VALUES ('00000001', '小狐', 1, 'fox', CURRENT_TIMESTAMP, 'offline')"
        )
        connection.commit()


def test_repository_persists_only_runtime_revision_and_presence(tmp_path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    _seed_elfie(db_path)
    repository = SQLiteNestStateAdapter(db_path)

    repository.save_catalog(WorldCatalog(nest_id="local-nest", revision=3, zones=()))
    repository.save_resident(
        PersistentResidentState(
            elfie_id="00000001",
            presence=ResidentPresence.ACTIVE,
        )
    )

    restored = repository.load_snapshot()
    with get_db(db_path) as connection:
        applied_revision = connection.execute(
            "SELECT applied_world_revision FROM nest_settings WHERE nest_id='local-nest'"
        ).fetchone()[0]
    assert applied_revision == 3
    assert restored.catalog is None
    assert restored.residents == (
        PersistentResidentState(
            elfie_id="00000001",
            presence=ResidentPresence.ACTIVE,
        ),
    )


def test_query_uses_public_defaults_without_writing_configuration(tmp_path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))

    snapshot = SQLiteNestStateAdapter(db_path).load_snapshot()

    assert snapshot.desired_bed_count == 4
    assert snapshot.elapsed_seconds == 0.0
    with get_db(db_path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM nest_settings").fetchone()[0] == 0
        )


def test_runtime_catalog_before_setup_does_not_create_configuration(tmp_path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    repository = SQLiteNestStateAdapter(db_path)

    repository.save_catalog(WorldCatalog(nest_id="local-nest", revision=1, zones=()))

    with get_db(db_path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM nest_settings").fetchone()[0] == 0
        )


def test_remove_resident_keeps_elfie_and_clears_bed(tmp_path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    _seed_elfie(db_path)
    with get_db(db_path) as connection:
        connection.execute(
            "UPDATE elfies SET status='online', bed_number=1 WHERE elfie_id='00000001'"
        )
        connection.commit()

    SQLiteNestStateAdapter(db_path).remove_resident("00000001")

    with get_db(db_path) as connection:
        row = connection.execute(
            "SELECT status, bed_number FROM elfies WHERE elfie_id='00000001'"
        ).fetchone()
    assert dict(row) == {"status": "offline", "bed_number": None}


@pytest.mark.parametrize(
    ("bed_number", "zone_id", "anchor_id"),
    ((2, "dorm-01", "dorm-01/bed-02"), (5, "dorm-02", "dorm-02/bed-01")),
)
def test_repository_exposes_persisted_bed_as_semantic_home_anchor(
    tmp_path, bed_number: int, zone_id: str, anchor_id: str
) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    _seed_elfie(db_path)
    if bed_number > 4:
        with get_db(db_path) as connection:
            connection.execute(
                "UPDATE nest_settings SET bed_count=8 WHERE nest_id='local-nest'"
            )
            connection.commit()
    SQLiteNestManagementAdapter(db_path).assign_bed("00000001", bed_number)

    assignments = SQLiteNestStateAdapter(db_path).load_home_assignments()

    assert assignments == {
        "00000001": PersistentResidentState(
            elfie_id="00000001",
            presence=ResidentPresence.PENDING_RUNTIME,
            home_zone_id=zone_id,
            home_anchor_id=anchor_id,
        )
    }
