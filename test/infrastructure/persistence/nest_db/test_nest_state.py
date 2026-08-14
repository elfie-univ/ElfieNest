from __future__ import annotations

import pytest

from infrastructure.persistence.nest_db.nest_management import (
    SQLiteNestManagementAdapter,
)
from infrastructure.persistence.nest_db.nest_state import SQLiteNestStateAdapter
from infrastructure.persistence.nest_db.store import get_db, init_db
from nest.state.models import (
    AnchorKind,
    EnvironmentDesiredState,
    EnvironmentRule,
    InteractionAnchor,
    LifePhase,
    PersistentResidentState,
    ResidentPresence,
    WorldCatalog,
    ZoneDescriptor,
)


def _seed_elfie(db_path: str) -> None:
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT INTO users(id, account_id, role, password_hash) "
            "VALUES (1, 'owner', 'owner', 'hash')"
        )
        catalog = WorldCatalog(
            nest_id="local-nest",
            revision=1,
            zones=(
                ZoneDescriptor(
                    zone_id="dorm-01",
                    label="Dorm 01",
                    order=0,
                    anchors=tuple(
                        InteractionAnchor(
                            anchor_id=f"dorm-01/bed-{index:02d}",
                            kind=AnchorKind.BED,
                            label=f"Bed {index:02d}",
                            order=index - 1,
                        )
                        for index in range(1, 5)
                    ),
                ),
            ),
        )
        connection.execute(
            "INSERT INTO nest_settings(nest_id, bed_count, tick_interval_sec) "
            "VALUES ('local-nest', 4, 1.0)"
        )
        connection.execute(
            "UPDATE nest_settings SET world_catalog_json=? WHERE nest_id='local-nest'",
            (catalog.model_dump_json(),),
        )
        connection.execute(
            "INSERT INTO elfies "
            "(elfie_id, name, owner_user_id, species, adopted_at, status) "
            "VALUES ('00000001', '小狐', 1, 'fox', CURRENT_TIMESTAMP, 'offline')"
        )
        connection.commit()


def test_repository_persists_runtime_catalog_revision_and_presence(tmp_path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    _seed_elfie(db_path)
    repository = SQLiteNestStateAdapter(db_path)

    catalog = WorldCatalog(nest_id="local-nest", revision=3, zones=())
    repository.save_catalog(catalog)
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
    assert restored.catalog == catalog
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


def test_repository_restores_clock_and_environment_rules(tmp_path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    _seed_elfie(db_path)
    repository = SQLiteNestStateAdapter(db_path)
    rules = (
        EnvironmentRule(
            rule_id="night-lights-off",
            phase=LifePhase.NIGHT,
            lights_on=False,
            quiet_mode=True,
        ),
    )

    repository.save_time_environment(
        elapsed_seconds=7200.0,
        clock_paused=True,
        time_scale=2.0,
        environment_desired=EnvironmentDesiredState(lights_on=False, quiet_mode=True),
        environment_rules=rules,
    )

    restored = repository.load_snapshot()

    assert restored.elapsed_seconds == 7200.0
    assert restored.clock_paused is True
    assert restored.time_scale == 2.0
    assert restored.environment_desired.lights_on is False
    assert restored.environment_rules == rules


def test_runtime_catalog_before_setup_does_not_create_configuration(tmp_path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    repository = SQLiteNestStateAdapter(db_path)

    repository.save_catalog(WorldCatalog(nest_id="local-nest", revision=1, zones=()))

    with get_db(db_path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM nest_settings").fetchone()[0] == 0
        )


def test_remove_resident_keeps_elfie_and_clears_home_anchor(tmp_path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    _seed_elfie(db_path)
    with get_db(db_path) as connection:
        connection.execute(
            "UPDATE elfies SET status='online', home_anchor_id='dorm-01/bed-01' "
            "WHERE elfie_id='00000001'"
        )
        connection.commit()

    SQLiteNestStateAdapter(db_path).remove_resident("00000001")

    with get_db(db_path) as connection:
        row = connection.execute(
            "SELECT status, home_anchor_id FROM elfies WHERE elfie_id='00000001'"
        ).fetchone()
    assert dict(row) == {"status": "offline", "home_anchor_id": None}


@pytest.mark.parametrize(
    ("anchor_id", "zone_id"),
    (("dorm-01/bed-02", "dorm-01"),),
)
def test_repository_exposes_persisted_bed_as_semantic_home_anchor(
    tmp_path, anchor_id: str, zone_id: str
) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    _seed_elfie(db_path)
    SQLiteNestManagementAdapter(db_path).assign_home("00000001", anchor_id)

    assignments = SQLiteNestStateAdapter(db_path).load_home_assignments()

    assert assignments == {
        "00000001": PersistentResidentState(
            elfie_id="00000001",
            presence=ResidentPresence.PENDING_RUNTIME,
            home_zone_id=zone_id,
            home_anchor_id=anchor_id,
        )
    }
