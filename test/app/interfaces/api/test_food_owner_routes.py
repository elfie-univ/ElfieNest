from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from ai_runtime.food.models import (
    FOOD_COMMON_ID,
    FOOD_EMERGENCY_ID,
    FoodPackage,
)
from ai_runtime.food.store import FoodCatalog
from app.infrastructure.persistence.food_assignments import (
    replace_food_access_users,
    set_elfie_main_food_id,
)
from app.infrastructure.persistence.store import get_db, init_db
from app.interfaces.api.app import create_app
from app.interfaces.api.food_owner_routes import _require_package

from ._helpers import create_test_owner, create_test_user


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_test_owner(db_path)
    user_id = create_test_user(db_path, "alice", "pass123")
    with get_db(db_path) as connection:
        connection.execute(
            """
            INSERT INTO elfies (elfie_id, name, owner_user_id, species, adopted_at, status)
            VALUES ('00000001', 'Test Elfie', ?, 'fox', '2026-07-31T00:00:00Z', 'offline')
            """,
            (user_id,),
        )
        connection.commit()
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
    ):
        app = create_app(engine=None, db_path=db_path, ws_port=9876)
        with TestClient(app) as test_client:
            test_client.app.state.test_user_id = user_id
            yield test_client


def _owner_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        data={"username": "owner", "password": "ownerchangeme"},
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": response.headers["X-CSRF-Token"]}


def test_system_foods_are_permanent_first_rows():
    catalog = FoodCatalog()
    assert [item.key for item in catalog.ordered_packages()] == [
        FOOD_EMERGENCY_ID,
        FOOD_COMMON_ID,
    ]
    with pytest.raises(ValueError, match="系统粮食不能归档"):
        FoodPackage(
            FOOD_COMMON_ID,
            "Common",
            system_role="common",
            enabled=False,
            archived=True,
        )


def test_custom_food_lifecycle_and_guarded_delete(client: TestClient) -> None:
    headers = _owner_headers(client)
    listed = client.get("/api/owner/runtime/foods/", headers=headers)
    assert [item["key"] for item in listed.json()["packages"]] == [
        FOOD_EMERGENCY_ID,
        FOOD_COMMON_ID,
    ]
    assert client.post(
        f"/api/owner/runtime/foods/{FOOD_COMMON_ID}/archive",
        headers=headers,
    ).status_code == 409
    assert client.delete(
        f"/api/owner/runtime/foods/{FOOD_EMERGENCY_ID}",
        headers=headers,
    ).status_code == 409

    created = client.post(
        "/api/owner/runtime/foods/",
        json={"display_name": "Private food", "roles": {}},
        headers=headers,
    )
    assert created.status_code == 201
    food_id = created.json()["food"]["key"]
    user_id = int(client.app.state.test_user_id)
    replace_food_access_users(client.app.state.db_path, food_id, (user_id,))
    set_elfie_main_food_id(client.app.state.db_path, "00000001", food_id)

    archived = client.post(
        f"/api/owner/runtime/foods/{food_id}/archive",
        headers=headers,
    )
    assert archived.status_code == 200
    assert client.delete(
        f"/api/owner/runtime/foods/{food_id}",
        headers=headers,
    ).status_code == 409

    replace_food_access_users(client.app.state.db_path, food_id, ())
    with get_db(client.app.state.db_path) as connection:
        connection.execute(
            "UPDATE elfies SET main_food_id = NULL WHERE elfie_id = ?",
            ("00000001",),
        )
        connection.commit()
    deleted = client.delete(
        f"/api/owner/runtime/foods/{food_id}",
        headers=headers,
    )
    assert deleted.status_code == 200
    assert food_id not in {item["key"] for item in deleted.json()["packages"]}


def test_missing_food_raises_not_found():
    with pytest.raises(HTTPException, match="未知粮食"):
        _require_package(FoodCatalog(), "food_missing")
