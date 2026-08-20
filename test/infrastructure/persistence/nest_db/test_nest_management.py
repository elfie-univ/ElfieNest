from __future__ import annotations

from infrastructure.persistence.nest_db.nest_management import (
    SQLiteNestManagementAdapter,
)
from infrastructure.persistence.nest_db.store import get_db, init_db
from nest import NestConfig
from nest.public import AnchorKind, InteractionAnchor, WorldCatalog, ZoneDescriptor


def _database(tmp_path) -> str:
    return init_db(str(tmp_path / "nest.db"))


def _seed_elfie(db_path: str, elfie_id: str) -> None:
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT OR IGNORE INTO users(id, account_id, role, password_hash) "
            "VALUES (1, 'owner', 'owner', 'hash')"
        )
        connection.execute(
            """INSERT INTO elfies(
                   elfie_id, name, owner_user_id, species, adopted_at, status
               ) VALUES (?, ?, 1, 'fox', CURRENT_TIMESTAMP, 'offline')""",
            (elfie_id, elfie_id),
        )
        connection.commit()


def _seed_nest(db_path: str) -> None:
    config = NestConfig()
    with get_db(db_path) as connection:
        connection.execute(
            """INSERT INTO nest_settings(nest_id, bed_count, tick_interval_sec)
               VALUES (?, ?, 1.0)""",
            (config.nest_id, config.bed_count),
        )
        catalog = WorldCatalog(
            nest_id=config.nest_id,
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
                        for index in range(1, config.bed_count + 1)
                    ),
                ),
            ),
        )
        connection.execute(
            "UPDATE nest_settings SET world_catalog_json=? WHERE nest_id=?",
            (catalog.model_dump_json(), config.nest_id),
        )
        connection.commit()


def test_query_returns_default_projection_without_writing(tmp_path) -> None:
    db_path = _database(tmp_path)
    adapter = SQLiteNestManagementAdapter(db_path)

    snapshot = adapter.load_snapshot()

    assert snapshot.desired_bed_count == NestConfig().bed_count
    assert snapshot.beds == ()
    with get_db(db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM nest_settings").fetchone()[0]
    assert count == 0


def test_query_reads_authoritative_configuration_and_assignments(tmp_path) -> None:
    db_path = _database(tmp_path)
    _seed_nest(db_path)
    _seed_elfie(db_path, "00000001")
    with get_db(db_path) as connection:
        connection.execute(
            "UPDATE nest_settings SET bed_count=6 WHERE nest_id='local-nest'"
        )
        connection.execute(
            "UPDATE elfies SET home_anchor_id='dorm-01/bed-01' "
            "WHERE elfie_id='00000001'"
        )
        connection.commit()
    adapter = SQLiteNestManagementAdapter(db_path)

    snapshot = adapter.load_snapshot()

    assert snapshot.desired_bed_count == 6
    assert snapshot.beds[0].occupant_id == "00000001"
