from app.infrastructure.persistence.nest_state_repository import (
    SQLiteNestStateRepository,
)
from app.infrastructure.persistence.store import get_db, init_db
from nest.state.models import PersistentResidentState, ResidentPresence, WorldCatalog


def _seed_elfie(db_path: str) -> None:
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT INTO users(id, username, role, password_hash) "
            "VALUES (1, 'owner', 'owner', 'hash')"
        )
        connection.execute(
            "INSERT INTO nest_settings(nest_id, bed_count, tick_interval_sec) "
            "VALUES ('local', 4, 1.0)"
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
    repository = SQLiteNestStateRepository(db_path)

    repository.save_catalog(
        WorldCatalog(nest_id="local-nest", revision=3, zones=())
    )
    repository.save_resident(
        PersistentResidentState(
            elfie_id="00000001",
            presence=ResidentPresence.ACTIVE,
        )
    )

    restored = repository.load_snapshot()
    with get_db(db_path) as connection:
        applied_revision = connection.execute(
            "SELECT applied_world_revision FROM nest_settings WHERE nest_id='local'"
        ).fetchone()[0]
    assert applied_revision == 3
    assert restored.catalog is None
    assert restored.residents == (
        PersistentResidentState(
            elfie_id="00000001",
            presence=ResidentPresence.ACTIVE,
        ),
    )


def test_remove_resident_keeps_elfie_and_clears_bed(tmp_path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    _seed_elfie(db_path)
    with get_db(db_path) as connection:
        connection.execute(
            "UPDATE elfies SET status='online', bed_number=1 WHERE elfie_id='00000001'"
        )
        connection.commit()

    SQLiteNestStateRepository(db_path).remove_resident("00000001")

    with get_db(db_path) as connection:
        row = connection.execute(
            "SELECT status, bed_number FROM elfies WHERE elfie_id='00000001'"
        ).fetchone()
    assert dict(row) == {"status": "offline", "bed_number": None}
