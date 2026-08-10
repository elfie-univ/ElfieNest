from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.accounts import AccountPrincipal, AccountRole
from app.features.nest_management import NestManagementService
from infrastructure.persistence.store import get_db, init_db
from app.interfaces.api.v1.admin.nest.routes import router
from app.interfaces.api.v1.auth import require_user
from infrastructure.persistence.nest_management import SQLiteNestManagementAdapter
from nest import NestConfig


def _principal(role: AccountRole = "owner") -> AccountPrincipal:
    return AccountPrincipal(
        user_id=1,
        account_id="owner",
        role=role,
        default_landing_page="/manage",
    )


def _client(tmp_path, role: str = "owner") -> tuple[TestClient, str]:
    db_path = init_db(str(tmp_path / "nest.db"))
    application = FastAPI()
    application.state.nest_management = NestManagementService(
        SQLiteNestManagementAdapter(db_path)
    )
    application.dependency_overrides[require_user] = lambda: _principal(role)
    application.include_router(router)
    return TestClient(application), db_path


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
        connection.commit()


def test_versioned_admin_nest_real_chain(tmp_path) -> None:
    client, db_path = _client(tmp_path)
    _seed_nest(db_path)
    _seed_elfie(db_path, "00000001")

    updated = client.put(
        "/api/v1/admin/nest/rooms/default/bed-count",
        json={"bed_count": 6},
    )
    assigned = client.put(
        "/api/v1/admin/nest/elfies/00000001/bed",
        json={"home_anchor_id": "bed-02"},
    )
    rooms = client.get("/api/v1/admin/nest/rooms")

    assert updated.status_code == 200
    assert updated.json() == {
        "desired_bed_count": 6,
        "applied_world_revision": None,
    }
    assert assigned.status_code == 200
    assert assigned.json()["home_anchor_id"] == "bed-02"
    assert rooms.status_code == 200
    assert rooms.json()["items"][0]["beds"][1]["occupant_id"] == "00000001"


def test_versioned_admin_nest_maps_conflict_to_error_envelope(tmp_path) -> None:
    client, db_path = _client(tmp_path)
    _seed_nest(db_path)
    _seed_elfie(db_path, "00000001")
    _seed_elfie(db_path, "00000002")
    client.put(
        "/api/v1/admin/nest/elfies/00000001/bed",
        json={"home_anchor_id": "bed-01"},
    )

    response = client.put(
        "/api/v1/admin/nest/elfies/00000002/bed",
        json={"home_anchor_id": "bed-01"},
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
    client, _ = _client(tmp_path, role="user")

    response = client.get("/api/v1/admin/nest/rooms")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "nest_management_forbidden"
