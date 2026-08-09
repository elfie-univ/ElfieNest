from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.persistence.store import get_db, init_db
from app.interfaces.api.app import create_app

from ._helpers import create_test_owner


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
        "/api/auth/login", data={"account_id": "owner", "password": "ownerchangeme"}
    )
    assert resp.status_code == 200
    return {"csrf_token": resp.headers.get("X-CSRF-Token", "")}


def _login_user(
    client: TestClient,
    account_id: str,
    password: str,
) -> dict[str, str]:
    resp = client.post(
        "/api/auth/login",
        data={"account_id": account_id, "password": password},
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
            "beds": [
                {
                    "id": number,
                    "anchor_id": f"bed-{number:02d}",
                    "kind": "bed",
                    "label": f"Bed {number:02d}",
                    "order": number - 1,
                    "active": True,
                    "occupant_id": None,
                    "occupant_name": None,
                    "occupant_owner_user_id": None,
                    "occupant_species_id": None,
                    "occupant_owner_account_id": None,
                    "occupant_owner_display_name": None,
                }
                for number in range(1, 5)
            ],
            "zones": [
                {
                    "zone_id": "beds",
                    "label": "Beds",
                    "order": 0,
                    "anchors": [
                        {
                            "id": number,
                            "anchor_id": f"bed-{number:02d}",
                            "kind": "bed",
                            "label": f"Bed {number:02d}",
                            "order": number - 1,
                            "active": True,
                            "occupant_id": None,
                            "occupant_name": None,
                            "occupant_owner_user_id": None,
                            "occupant_species_id": None,
                            "occupant_owner_account_id": None,
                            "occupant_owner_display_name": None,
                        }
                        for number in range(1, 5)
                    ],
                }
            ],
        }
    ]


def test_bed_count_updates_desired_state_not_python_bed_geometry(
    client: TestClient,
) -> None:
    tokens = _login_owner(client)
    headers = _headers(tokens["csrf_token"])

    resp = client.put(
        "/api/owner/nest/rooms/default/bed-count",
        json={"bed_count": 6},
        headers=headers,
    )
    rooms = client.get("/api/owner/nest/rooms", headers=headers).json()

    assert resp.status_code == 200
    assert resp.json()["desired_bed_count"] == 6
    assert rooms[0]["desired_bed_count"] == 6
    assert [bed["anchor_id"] for bed in rooms[0]["beds"]] == [
        f"bed-{number:02d}" for number in range(1, 7)
    ]

@pytest.mark.parametrize("bed_count", [1, 3, 33, 64])
def test_bed_count_rejects_values_outside_production_range(
    client: TestClient,
    bed_count: int,
) -> None:
    tokens = _login_owner(client)
    headers = _headers(tokens["csrf_token"])

    resp = client.put(
        "/api/owner/nest/rooms/default/bed-count",
        json={"bed_count": bed_count},
        headers=headers,
    )

    assert resp.status_code == 422
    assert "4 到 32" in resp.text


def test_semantic_bed_numbers_are_visible_without_grid_fields(
    client: TestClient,
    db_path: str,
) -> None:
    tokens = _login_owner(client)

    resp = client.get("/api/owner/nest/rooms", headers=_headers(tokens["csrf_token"]))

    assert resp.status_code == 200
    beds = resp.json()[0]["beds"]
    assert [bed["anchor_id"] for bed in beds] == [
        "bed-01",
        "bed-02",
        "bed-03",
        "bed-04",
    ]
    assert all("grid_x" not in bed and "grid_y" not in bed for bed in beds)


def test_assign_home_rejects_occupied_bed(client: TestClient, db_path: str) -> None:
    _seed_elfie(db_path, "00000001")
    _seed_elfie(db_path, "00000002")
    tokens = _login_owner(client)
    headers = _headers(tokens["csrf_token"])

    first = client.put(
        "/api/owner/nest/elfies/00000001/bed",
        json={"home_anchor_id": "bed-01"},
        headers=headers,
    )
    second = client.put(
        "/api/owner/nest/elfies/00000002/bed",
        json={"home_anchor_id": "bed-01"},
        headers=headers,
    )

    assert first.status_code == 200
    assert first.json()["home_anchor_id"] == "bed-01"
    assert second.status_code == 409


def _seed_elfie(
    db_path: str,
    elfie_id: str,
    *,
    owner_account_id: str = "owner",
) -> None:
    with get_db(db_path) as conn:
        owner_id = conn.execute(
            "SELECT id FROM users WHERE account_id = ?",
            (owner_account_id,),
        ).fetchone()["id"]
        conn.execute(
            """
            INSERT INTO elfies
                (elfie_id, name, owner_user_id, species, adopted_at, status)
            VALUES (?, ?, ?, 'fox', CURRENT_TIMESTAMP, 'offline')
            """,
            (elfie_id, elfie_id, owner_id),
        )
        conn.commit()
