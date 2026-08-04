from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from ai_runtime.food.models import FOOD_COMMON_ID, FOOD_EMERGENCY_ID, FoodPackage
from ai_runtime.food.planner import ModelEvidence
from ai_runtime.food.store import FoodCatalog
from app.infrastructure.persistence.food_packages import SQLiteFoodPackageRepository
from app.infrastructure.persistence.store import get_db, init_db
from app.interfaces.api.app import create_app
from app.interfaces.api.food_catalog_support import require_package

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
        data={"account_id": "owner", "password": "ownerchangeme"},
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": response.headers["X-CSRF-Token"]}


def _fresh_evidence() -> dict[str, ModelEvidence]:
    return {
        "cloud/main": ModelEvidence(
            model="cloud/main",
            capabilities=frozenset({"text"}),
            verified=True,
            observed_at=datetime.now(timezone.utc).isoformat(),
        )
    }


@pytest.fixture(autouse=True)
def food_api_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.interfaces.api import food_catalog_support

    monkeypatch.setattr(food_catalog_support, "query_model_evidence", _fresh_evidence)
    monkeypatch.setattr(
        food_catalog_support,
        "validate_food_catalog_model_references",
        lambda _catalog: None,
    )


def _repository(client: TestClient) -> SQLiteFoodPackageRepository:
    return SQLiteFoodPackageRepository(client.app.state.db_path)


def _seed_custom_food(client: TestClient, key: str = "food_custom") -> FoodPackage:
    package = FoodPackage(key, "自定义粮", enabled=False)
    _repository(client).create(package)
    return package


def test_system_foods_are_permanent_first_rows(client: TestClient) -> None:
    headers = _owner_headers(client)
    response = client.get("/api/owner/runtime/foods/", headers=headers)

    assert response.status_code == 200
    assert [item["key"] for item in response.json()["packages"]] == [
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


def test_generation_preview_does_not_write_a_new_row(
    client: TestClient,
) -> None:
    headers = _owner_headers(client)
    before = {item.key for item in _repository(client).list()}
    response = client.post(
        "/api/owner/runtime/foods/generation-preview",
        json={
            "display_name": "Preview food",
            "connection_ids": ["cloud"],
            "local_first": False,
            "allow_remote": True,
            "visibility_mode": "global",
            "visible_user_ids": [],
        },
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["food_id"] is None
    assert response.json()["candidate"]["display_name"] == "Preview food"
    assert {item.key for item in _repository(client).list()} == before


def test_create_persists_complete_row_and_flat_visibility(
    client: TestClient,
) -> None:
    headers = _owner_headers(client)
    user_id = int(client.app.state.test_user_id)
    response = client.post(
        "/api/owner/runtime/foods/",
        json={
            "display_name": "Created food",
            "enabled": True,
            "roles": {"primary": {"model": "cloud/main"}, "fallback": None},
            "visibility_mode": "users",
            "visible_user_ids": [user_id],
        },
        headers=headers,
    )

    assert response.status_code == 201, response.text
    food_id = response.json()["food"]["key"]
    saved = _repository(client).get(food_id)
    assert saved is not None
    assert saved.enabled is True
    assert saved.primary is not None and saved.primary.model == "cloud/main"
    assert saved.visibility_mode == "users"
    assert saved.visible_user_ids == (user_id,)


def test_invalid_visibility_does_not_mutate_existing_row(client: TestClient) -> None:
    headers = _owner_headers(client)
    original = _seed_custom_food(client)
    response = client.put(
        f"/api/owner/runtime/foods/{original.key}",
        json={
            "display_name": "Changed",
            "roles": {},
            "visibility_mode": "users",
            "visible_user_ids": [True],
        },
        headers=headers,
    )

    assert response.status_code == 422
    assert _repository(client).get(original.key) == original


def test_food_owner_routes_reject_string_booleans_and_system_visibility_changes(
    client: TestClient,
) -> None:
    headers = _owner_headers(client)
    invalid_boolean = client.post(
        "/api/owner/runtime/foods/generation-preview",
        json={
            "display_name": "严格布尔值",
            "connection_ids": [],
            "local_first": "false",
            "allow_remote": True,
        },
        headers=headers,
    )
    assert invalid_boolean.status_code == 422
    assert "local_first 必须是布尔值" in invalid_boolean.json()["detail"]

    empty_scope = client.post(
        "/api/owner/runtime/foods/generation-preview",
        json={
            "display_name": "空来源",
            "connection_ids": [],
            "local_first": False,
            "allow_remote": True,
        },
        headers=headers,
    )
    assert empty_scope.status_code == 422
    assert "至少选择一个生成来源" in empty_scope.json()["detail"]

    invalid_system_visibility = client.put(
        f"/api/owner/runtime/foods/{FOOD_COMMON_ID}",
        json={"visibility_mode": "users", "visible_user_ids": [client.app.state.test_user_id]},
        headers=headers,
    )
    assert invalid_system_visibility.status_code == 422
    stored = _repository(client).get(FOOD_COMMON_ID)
    assert stored is not None
    assert stored.visibility_mode == "global"
    assert stored.visible_user_ids == ()
    assert client.post(
        f"/api/owner/runtime/foods/{FOOD_COMMON_ID}/enable",
        headers=headers,
    ).status_code == 422


def test_archived_custom_food_delete_respects_elfie_reference(client: TestClient) -> None:
    headers = _owner_headers(client)
    package = _seed_custom_food(client, "food_lifecycle")
    with get_db(client.app.state.db_path) as connection:
        connection.execute(
            "UPDATE elfies SET main_food_id=? WHERE elfie_id=?",
            (package.key, "00000001"),
        )
        connection.commit()

    assert client.post(
        f"/api/owner/runtime/foods/{package.key}/archive",
        headers=headers,
    ).status_code == 200
    assert client.delete(
        f"/api/owner/runtime/foods/{package.key}",
        headers=headers,
    ).status_code == 409

    with get_db(client.app.state.db_path) as connection:
        connection.execute(
            "UPDATE elfies SET main_food_id=NULL WHERE elfie_id=?",
            ("00000001",),
        )
        connection.commit()
    assert client.delete(
        f"/api/owner/runtime/foods/{package.key}",
        headers=headers,
    ).status_code == 200


def test_missing_food_raises_not_found() -> None:
    with pytest.raises(HTTPException, match="未知粮食"):
        require_package(FoodCatalog(), "missing")
