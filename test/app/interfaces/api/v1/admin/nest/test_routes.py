from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.accounts import AccountPrincipal, AccountRole
from app.features.nest_management import NestManagementService
from app.interfaces.api.v1.admin.nest.routes import router
from app.interfaces.api.v1.auth import require_user
from app.orchestration.nest_session import (
    ElfieNestEngine,
    LiveNestManagementCommands,
)
from elfie import Elfie
from infrastructure.persistence.nest_db.nest_management import (
    SQLiteNestManagementAdapter,
)
from infrastructure.persistence.nest_db.nest_state import SQLiteNestStateAdapter
from infrastructure.persistence.nest_db.store import get_db, init_db
from nest import NestConfig
from nest.public import AnchorKind, InteractionAnchor, WorldCatalog, ZoneDescriptor
from test.app.orchestration.nest_session.fakes import FakeWorldRuntime


def _principal(role: AccountRole = "owner") -> AccountPrincipal:
    return AccountPrincipal(
        user_id=1,
        account_id="owner",
        role=role,
        default_landing_page="/manage",
    )


def _client(
    tmp_path,
    role: str = "owner",
    *,
    elfie_ids: tuple[str, ...] = (),
) -> tuple[TestClient, str, ElfieNestEngine]:
    db_path = init_db(str(tmp_path / "nest.db"))
    _seed_nest(db_path)
    for elfie_id in elfie_ids:
        _seed_elfie(db_path, elfie_id)
    engine = ElfieNestEngine(
        FakeWorldRuntime(),
        state_store=SQLiteNestStateAdapter(db_path),
    )
    for elfie_id in elfie_ids:
        engine.session.register_elfie(elfie_id, MagicMock(spec=Elfie))
    query = SQLiteNestManagementAdapter(db_path)
    application = FastAPI()
    application.state.nest_management = NestManagementService(
        query,
        LiveNestManagementCommands(engine.session),
    )
    application.dependency_overrides[require_user] = lambda: _principal(role)
    application.include_router(router)
    return TestClient(application), db_path, engine


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


def test_versioned_admin_nest_real_chain(tmp_path) -> None:
    client, _, _ = _client(tmp_path, elfie_ids=("00000001",))

    updated = client.put(
        "/api/v1/admin/nest/rooms/default/bed-count",
        json={"bed_count": 6},
    )
    assigned = client.put(
        "/api/v1/admin/nest/elfies/00000001/bed",
        json={"home_anchor_id": "dorm-01/bed-02"},
    )
    rooms = client.get("/api/v1/admin/nest/rooms")

    assert updated.status_code == 200
    assert updated.json() == {
        "desired_bed_count": 6,
        "applied_world_revision": 1,
    }
    assert assigned.status_code == 200
    assert assigned.json()["home_anchor_id"] == "dorm-01/bed-02"
    assert rooms.status_code == 200
    assert rooms.json()["items"][0]["beds"][1]["occupant_id"] == "00000001"


def test_versioned_admin_nest_maps_conflict_to_error_envelope(tmp_path) -> None:
    client, _, _ = _client(
        tmp_path,
        elfie_ids=("00000001", "00000002"),
    )
    client.put(
        "/api/v1/admin/nest/elfies/00000001/bed",
        json={"home_anchor_id": "dorm-01/bed-01"},
    )

    response = client.put(
        "/api/v1/admin/nest/elfies/00000002/bed",
        json={"home_anchor_id": "dorm-01/bed-01"},
    )

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "nest_bed_conflict",
            "message": "bed already occupied",
            "details": {},
        }
    }


def test_versioned_admin_nest_authorizes_in_feature(tmp_path) -> None:
    client, _, _ = _client(tmp_path, role="user")

    response = client.get("/api/v1/admin/nest/rooms")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "nest_management_forbidden"


def test_versioned_admin_bed_count_survives_ticks_and_restart(tmp_path) -> None:
    client, db_path, engine = _client(tmp_path)

    updated = client.put(
        "/api/v1/admin/nest/rooms/default/bed-count",
        json={"bed_count": 32},
    )
    for _ in range(3):
        engine.tick_once(1.0)

    rooms = client.get("/api/v1/admin/nest/rooms")
    persisted = SQLiteNestStateAdapter(db_path).load_snapshot()
    restarted = ElfieNestEngine(
        FakeWorldRuntime(),
        state_store=SQLiteNestStateAdapter(db_path),
    )

    assert updated.status_code == 200
    assert rooms.json()["items"][0]["desired_bed_count"] == 32
    assert persisted is not None
    assert persisted.desired_bed_count == 32
    assert restarted.session.nest.desired_bed_count == 32
