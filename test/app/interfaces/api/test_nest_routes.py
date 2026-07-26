from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.persistence.store import get_db, init_db
from app.interfaces.api.app import create_app

from ._helpers import create_test_owner, create_test_user


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "nest.db")


@pytest.fixture
def client(db_path: str):
    init_db(db_path)
    create_test_owner(db_path)
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        with TestClient(application) as c:
            yield c


def _login_owner(client: TestClient) -> dict[str, str]:
    resp = client.post(
        "/api/auth/login", data={"username": "owner", "password": "ownerchangeme"}
    )
    assert resp.status_code == 200
    return {"csrf_token": resp.headers.get("X-CSRF-Token", "")}


def _login_user(
    client: TestClient,
    username: str,
    password: str,
) -> dict[str, str]:
    resp = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )
    assert resp.status_code == 200
    return {"csrf_token": resp.headers.get("X-CSRF-Token", "")}


def _headers(csrf_token: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf_token, "Content-Type": "application/json"}


def test_default_semantic_nest_has_desired_count_without_coordinates(
    client: TestClient,
) -> None:
    tokens = _login_owner(client)

    resp = client.get("/api/owner/nest/rooms", headers=_headers(tokens["csrf_token"]))

    assert resp.status_code == 200
    rooms = resp.json()
    assert rooms == [
        {
            "id": "local-nest",
            "name": "Local Nest",
            "desired_bed_count": 4,
            "applied_world_revision": None,
            "beds": [],
            "zones": [],
        }
    ]


def test_bed_count_updates_desired_state_not_python_bed_geometry(
    client: TestClient,
) -> None:
    tokens = _login_owner(client)
    headers = _headers(tokens["csrf_token"])

    resp = client.put(
        "/api/owner/nest/rooms/local-nest/bed-count",
        json={"bed_count": 6},
        headers=headers,
    )
    rooms = client.get("/api/owner/nest/rooms", headers=headers).json()

    assert resp.status_code == 200
    assert resp.json()["desired_bed_count"] == 6
    assert rooms[0]["desired_bed_count"] == 6
    assert rooms[0]["beds"] == []


def test_bed_count_rejects_values_above_semantic_runtime_limit(
    client: TestClient,
) -> None:
    tokens = _login_owner(client)
    headers = _headers(tokens["csrf_token"])

    resp = client.put(
        "/api/owner/nest/rooms/default/bed-count",
        json={"bed_count": 64},
        headers=headers,
    )

    assert resp.status_code == 422


def test_create_room_and_coordinate_update_are_gone(client: TestClient) -> None:
    tokens = _login_owner(client)
    headers = _headers(tokens["csrf_token"])

    create_resp = client.post(
        "/api/owner/nest/rooms",
        json={"name": "Oversized Nest", "max_capacity": 64},
        headers=headers,
    )
    coordinate_resp = client.put(
        "/api/owner/nest/beds/dorm-01-bed-01",
        json={"grid_x": 10, "grid_y": 20},
        headers=headers,
    )

    assert create_resp.status_code == 410
    assert coordinate_resp.status_code == 410


def test_runtime_manifest_bed_anchors_are_visible_without_grid_fields(
    client: TestClient,
    db_path: str,
) -> None:
    _seed_manifest(db_path, bed_count=2)
    tokens = _login_owner(client)

    resp = client.get("/api/owner/nest/rooms", headers=_headers(tokens["csrf_token"]))

    assert resp.status_code == 200
    beds = resp.json()[0]["beds"]
    assert [bed["anchor_id"] for bed in beds] == ["dorm-01/bed-01", "dorm-01/bed-02"]
    assert all("grid_x" not in bed and "grid_y" not in bed for bed in beds)


def test_assign_home_rejects_occupied_bed(client: TestClient, db_path: str) -> None:
    _seed_manifest(db_path, bed_count=1)
    _seed_elfie(db_path, "fox-1")
    _seed_elfie(db_path, "dog-1")
    tokens = _login_owner(client)
    headers = _headers(tokens["csrf_token"])

    first = client.put(
        "/api/owner/nest/elfies/fox-1/bed",
        json={"home_anchor_id": "dorm-01/bed-01"},
        headers=headers,
    )
    second = client.put(
        "/api/owner/nest/elfies/dog-1/bed",
        json={"home_anchor_id": "dorm-01/bed-01"},
        headers=headers,
    )

    assert first.status_code == 200
    assert first.json()["home_anchor_id"] == "dorm-01/bed-01"
    assert second.status_code == 409


def test_user_room_view_redacts_another_users_occupant(
    client: TestClient,
    db_path: str,
) -> None:
    _seed_manifest(db_path, bed_count=1)
    create_test_user(db_path, "alice", "pass123")
    create_test_user(db_path, "bob", "bobpass")
    _seed_elfie(db_path, "bob-fox", owner_username="bob")
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT INTO nest_memberships (elfie_id, presence) VALUES (?, 'active')",
            ("bob-fox",),
        )
        conn.execute(
            """
            INSERT INTO nest_home_assignments
                (elfie_id, home_zone_id, home_anchor_id)
            VALUES (?, 'dorm-01', 'dorm-01/bed-01')
            """,
            ("bob-fox",),
        )
        conn.commit()
    tokens = _login_user(client, "alice", "pass123")

    response = client.get(
        "/api/user/nest/rooms",
        headers=_headers(tokens["csrf_token"]),
    )

    assert response.status_code == 200
    bed = response.json()[0]["beds"][0]
    assert bed["occupant_id"] is None
    assert bed["occupant_name"] is None
    assert bed["occupant_owner_username"] is None


def _seed_manifest(db_path: str, bed_count: int) -> None:
    with get_db(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO nest_config
                (nest_id, desired_bed_count, applied_world_revision)
            VALUES ('local-nest', ?, 7)
            """,
            (bed_count,),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO nest_zones
                (zone_id, nest_id, label, zone_order, active)
            VALUES ('dorm-01', 'local-nest', '01 宿舍', 0, 1)
            """
        )
        for index in range(bed_count):
            conn.execute(
                """
                INSERT OR REPLACE INTO nest_anchors
                    (anchor_id, zone_id, kind, label, anchor_order, active)
                VALUES (?, 'dorm-01', 'bed', ?, ?, 1)
                """,
                (
                    f"dorm-01/bed-{index + 1:02d}",
                    f"Bed {index + 1}",
                    index,
                ),
            )
        conn.commit()


def _seed_elfie(
    db_path: str,
    elfie_id: str,
    *,
    owner_username: str = "owner",
) -> None:
    with get_db(db_path) as conn:
        owner_id = conn.execute(
            "SELECT id FROM users WHERE username = ?",
            (owner_username,),
        ).fetchone()["id"]
        conn.execute(
            """
            INSERT INTO elfie_registry
                (elfie_id, name, owner_user_id, anatomy_type)
            VALUES (?, ?, ?, 'quadruped')
            """,
            (elfie_id, elfie_id, owner_id),
        )
        conn.commit()
