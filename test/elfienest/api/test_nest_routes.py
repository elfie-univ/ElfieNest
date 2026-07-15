from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from elfienest.api.app import create_app
from elfienest.persistence.store import get_db, init_db

from ._helpers import create_test_admin


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "nest.db")


@pytest.fixture
def client(db_path: str):
    init_db(db_path)
    create_test_admin(db_path)
    with (
        patch("elfienest.api.app.AuthenticatedWSManager.start"),
        patch("elfienest.api.app.AuthenticatedWSManager.stop"),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        with TestClient(application) as c:
            yield c


def _login_admin(client: TestClient) -> dict[str, str]:
    resp = client.post("/api/auth/login", data={"username": "admin", "password": "adminchangeme"})
    assert resp.status_code == 200
    return {"csrf_token": resp.headers.get("X-CSRF-Token", "")}


def _headers(csrf_token: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf_token, "Content-Type": "application/json"}


def test_default_room_is_created_when_rooms_are_empty(client: TestClient) -> None:
    tokens = _login_admin(client)

    resp = client.get("/api/admin/nest/rooms", headers=_headers(tokens["csrf_token"]))

    assert resp.status_code == 200
    rooms = resp.json()
    assert len(rooms) == 1
    assert rooms[0]["name"] == "Main Nest"
    assert len(rooms[0]["beds"]) == 4
    assert [(bed["grid_x"], bed["grid_y"]) for bed in rooms[0]["beds"]] == [
        (18, 34),
        (39, 34),
        (60, 34),
        (18, 54),
    ]


def test_bed_count_adds_beds_in_dorm_row_layout(client: TestClient) -> None:
    tokens = _login_admin(client)
    headers = _headers(tokens["csrf_token"])
    room = client.get("/api/admin/nest/rooms", headers=headers).json()[0]

    resp = client.put(
        f"/api/admin/nest/rooms/{room['id']}/bed-count",
        json={"bed_count": 6},
        headers=headers,
    )
    rooms = client.get("/api/admin/nest/rooms", headers=headers).json()

    assert resp.status_code == 200
    assert resp.json()["bed_count"] == 6
    assert [(bed["grid_x"], bed["grid_y"]) for bed in rooms[0]["beds"]] == [
        (18, 34),
        (39, 34),
        (60, 34),
        (18, 54),
        (39, 54),
        (60, 54),
    ]


def test_bed_count_supports_four_bed_groups_beyond_twelve(client: TestClient) -> None:
    tokens = _login_admin(client)
    headers = _headers(tokens["csrf_token"])
    room = client.get("/api/admin/nest/rooms", headers=headers).json()[0]

    resp = client.put(
        f"/api/admin/nest/rooms/{room['id']}/bed-count",
        json={"bed_count": 16},
        headers=headers,
    )
    rooms = client.get("/api/admin/nest/rooms", headers=headers).json()

    assert resp.status_code == 200
    assert resp.json()["bed_count"] == 16
    assert len(rooms[0]["beds"]) == 16
    assert rooms[0]["beds"][-1]["name"] == "Bed 16"


def test_bed_count_clamps_to_maximum_thirty_two(client: TestClient) -> None:
    tokens = _login_admin(client)
    headers = _headers(tokens["csrf_token"])
    room = client.get("/api/admin/nest/rooms", headers=headers).json()[0]

    resp = client.put(
        f"/api/admin/nest/rooms/{room['id']}/bed-count",
        json={"bed_count": 64},
        headers=headers,
    )
    rooms = client.get("/api/admin/nest/rooms", headers=headers).json()

    assert resp.status_code == 200
    assert resp.json()["requested_count"] == 32
    assert resp.json()["bed_count"] == 32
    assert len(rooms[0]["beds"]) == 32


def test_create_room_clamps_capacity_to_maximum_thirty_two(client: TestClient) -> None:
    tokens = _login_admin(client)
    headers = _headers(tokens["csrf_token"])

    resp = client.post(
        "/api/admin/nest/rooms",
        json={"name": "Oversized Nest", "max_capacity": 64},
        headers=headers,
    )
    rooms = client.get("/api/admin/nest/rooms", headers=headers).json()
    created_room = next(room for room in rooms if room["id"] == resp.json()["id"])

    assert resp.status_code == 200
    assert resp.json()["max_capacity"] == 32
    assert len(created_room["beds"]) == 32


def test_bed_count_persists_after_reloading_rooms(client: TestClient) -> None:
    tokens = _login_admin(client)
    headers = _headers(tokens["csrf_token"])
    room = client.get("/api/admin/nest/rooms", headers=headers).json()[0]

    resp = client.put(
        f"/api/admin/nest/rooms/{room['id']}/bed-count",
        json={"bed_count": 23},
        headers=headers,
    )
    reloaded_resp = client.get("/api/admin/nest/rooms", headers=headers)
    second_reloaded_resp = client.get("/api/admin/nest/rooms", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["bed_count"] == 23
    assert reloaded_resp.status_code == 200
    assert len(reloaded_resp.json()[0]["beds"]) == 23
    assert len(second_reloaded_resp.json()[0]["beds"]) == 23


def test_default_room_bed_count_endpoint_persists_five_beds(client: TestClient) -> None:
    tokens = _login_admin(client)
    headers = _headers(tokens["csrf_token"])

    resp = client.put(
        "/api/admin/nest/rooms/default/bed-count",
        json={"bed_count": 5},
        headers=headers,
    )
    reloaded_resp = client.get("/api/admin/nest/rooms", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["bed_count"] == 5
    assert reloaded_resp.status_code == 200
    assert len(reloaded_resp.json()[0]["beds"]) == 5


def test_update_bed_count_clamps_to_minimum_four_and_preserves_occupied_beds(client: TestClient, db_path: str) -> None:
    tokens = _login_admin(client)
    headers = _headers(tokens["csrf_token"])
    room = client.get("/api/admin/nest/rooms", headers=headers).json()[0]
    occupied_bed_id = room["beds"][-1]["id"]

    with get_db(db_path) as conn:
        admin_id = conn.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()["id"]
        conn.execute(
            "INSERT INTO elfie_registry (elfie_id, name, owner_user_id, anatomy_type, bed_id) VALUES (?, ?, ?, ?, ?)",
            ("elfie_occupied", "占床精灵", admin_id, "biped", occupied_bed_id),
        )
        conn.commit()

    resp = client.put(
        f"/api/admin/nest/rooms/{room['id']}/bed-count",
        json={"bed_count": 2},
        headers=headers,
    )
    rooms = client.get("/api/admin/nest/rooms", headers=headers).json()
    bed_ids = {bed["id"] for bed in rooms[0]["beds"]}

    assert resp.status_code == 200
    assert resp.json()["requested_count"] == 4
    assert resp.json()["bed_count"] == 4
    assert occupied_bed_id in bed_ids
