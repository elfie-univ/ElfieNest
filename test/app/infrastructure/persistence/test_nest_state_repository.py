from app.infrastructure.persistence.nest_state_repository import (
    SQLiteNestStateRepository,
)
from app.infrastructure.persistence.store import get_db, init_db
from nest.state.models import (
    AnchorKind,
    InteractionAnchor,
    PersistentResidentState,
    ResidentPresence,
    WorldCatalog,
    ZoneDescriptor,
)


def test_sqlite_nest_state_repository_restores_catalog_home_and_clock(
    tmp_path,
) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        owner_id = connection.execute(
            """
            INSERT INTO users (username, password_hash, role)
            VALUES ('owner', 'hash', 'owner')
            """
        ).lastrowid
        connection.execute(
            """
            INSERT INTO elfie_registry
                (elfie_id, owner_user_id, name, species_id, config_dir)
            VALUES ('fox-1', ?, '小狐', 'fox', '/tmp/fox-1')
            """,
            (owner_id,),
        )
        connection.execute(
            """
            UPDATE nest_config
            SET clock_anchor_seconds = 12.5
            WHERE nest_id = 'local-nest'
            """
        )
        connection.commit()
    repository = SQLiteNestStateRepository(db_path)
    catalog = _catalog()

    repository.save_catalog(catalog)
    repository.save_resident(
        PersistentResidentState(
            elfie_id="fox-1",
            presence=ResidentPresence.ACTIVE,
            home_zone_id="dorm-01",
            home_anchor_id="dorm-01/bed-01",
        )
    )
    restored = repository.load_snapshot()

    assert restored.elapsed_seconds == 12.5
    assert restored.catalog == catalog
    assert restored.residents[0].home_anchor_id == "dorm-01/bed-01"


def test_sqlite_nest_state_repository_removes_membership_atomically(
    tmp_path,
) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        owner_id = connection.execute(
            """
            INSERT INTO users (username, password_hash, role)
            VALUES ('owner', 'hash', 'owner')
            """
        ).lastrowid
        connection.execute(
            """
            INSERT INTO elfie_registry
                (elfie_id, owner_user_id, name, species_id, config_dir)
            VALUES ('fox-1', ?, '小狐', 'fox', '/tmp/fox-1')
            """,
            (owner_id,),
        )
        connection.commit()
    repository = SQLiteNestStateRepository(db_path)
    repository.save_catalog(_catalog())
    repository.save_resident(
        PersistentResidentState(
            elfie_id="fox-1",
            presence=ResidentPresence.PENDING_RUNTIME,
        )
    )

    repository.remove_resident("fox-1")

    assert repository.load_snapshot().residents == ()


def _catalog() -> WorldCatalog:
    return WorldCatalog(
        nest_id="local-nest",
        revision=3,
        zones=(
            ZoneDescriptor(
                zone_id="dorm-01",
                label="01 宿舍",
                order=0,
                anchors=(
                    InteractionAnchor(
                        anchor_id="dorm-01/bed-01",
                        kind=AnchorKind.BED,
                        label="01-01 床位",
                        order=0,
                    ),
                ),
            ),
        ),
    )
