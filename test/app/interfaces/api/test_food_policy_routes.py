from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from ai_runtime.food.models import ExecutionProfile, FoodRecipe
from ai_runtime.food.store import FoodCatalog, FoodCatalogStore
from app.infrastructure.persistence.store import get_db, init_db
from app.interfaces.api.app import create_app

from ._helpers import create_test_owner


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "nest.db")


@pytest.fixture
def food_catalog_path(tmp_path: Path) -> Path:
    return tmp_path / "configs" / "food-packages.yaml"


@pytest.fixture
def client(db_path: str, food_catalog_path: Path, tmp_path: Path):
    init_db(db_path)
    create_test_owner(db_path)
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
        patch(
            "app.interfaces.api.food_policy_routes._FOOD_CATALOG_PATH",
            food_catalog_path,
        ),
        patch(
            "app.interfaces.api.food_owner_routes._FOOD_CATALOG_PATH",
            food_catalog_path,
        ),
        patch(
            "app.interfaces.api.food_owner_routes._FOOD_HISTORY_DIR",
            tmp_path / "food-history",
        ),
        patch(
            "app.interfaces.api.food_owner_routes._MODEL_EVIDENCE_PATH",
            tmp_path / "model-evidence.yaml",
        ),
    ):
        app = create_app(engine=None, db_path=db_path, ws_port=9876)
        with TestClient(app) as test_client:
            yield test_client


def headers(csrf):
    return {"X-CSRF-Token": csrf, "Content-Type": "application/json"}


def test_user_can_configure_only_food_keys_for_owned_elfie(client):
    owner = client.post(
        "/api/auth/login", data={"username": "owner", "password": "ownerchangeme"}
    )
    csrf = owner.headers["X-CSRF-Token"]
    created = client.post(
        "/api/owner/users",
        json={"username": "alice", "password": "pass123", "role": "user"},
        headers=headers(csrf),
    )
    assert created.status_code == 201
    login = client.post(
        "/api/auth/login", data={"username": "alice", "password": "pass123"}
    )
    user_csrf = login.headers["X-CSRF-Token"]
    adopted = client.post(
        "/api/user/adopt",
        json={
            "name": "小白",
            "anatomy_type": "biped",
            "personality_style": "好奇探索",
            "height": "standard",
            "build": "standard",
        },
        headers=headers(user_csrf),
    )
    elfie_id = adopted.json()["elfie_id"]

    response = client.put(
        f"/api/user/elfies/{elfie_id}/food-policy/",
        json={
            "default_food": "standard",
            "allowed_foods": ["coarse", "standard", "focus"],
            "fallback_food": "coarse",
        },
        headers=headers(user_csrf),
    )

    assert response.status_code == 200, response.text
    assert response.json()["allowed_foods"] == ["coarse", "standard", "focus"]

    loaded = client.get(
        f"/api/user/elfies/{elfie_id}/food-policy/",
        headers=headers(user_csrf),
    )
    assert loaded.json()["default_food"] == "standard"


def test_owner_can_edit_a_registered_elfies_food_policy(client):
    """管理台可只修改粮食策略，不暴露或修改精灵档案。"""
    owner = client.post(
        "/api/auth/login", data={"username": "owner", "password": "ownerchangeme"}
    )
    csrf = owner.headers["X-CSRF-Token"]
    created = client.post(
        "/api/owner/users",
        json={"username": "alice", "password": "pass123", "role": "user"},
        headers=headers(csrf),
    )
    assert created.status_code == 201
    login = client.post(
        "/api/auth/login", data={"username": "alice", "password": "pass123"}
    )
    user_csrf = login.headers["X-CSRF-Token"]
    adopted = client.post(
        "/api/user/adopt",
        json={
            "name": "小白",
            "anatomy_type": "biped",
            "personality_style": "好奇探索",
            "height": "standard",
            "build": "standard",
        },
        headers=headers(user_csrf),
    )
    owner = client.post(
        "/api/auth/login", data={"username": "owner", "password": "ownerchangeme"}
    )
    csrf = owner.headers["X-CSRF-Token"]

    response = client.put(
        f"/api/user/elfies/{adopted.json()['elfie_id']}/food-policy/",
        json={
            "default_food": "focus",
            "allowed_foods": ["coarse", "focus"],
            "fallback_food": "coarse",
        },
        headers=headers(csrf),
    )

    assert response.status_code == 200, response.text
    assert response.json()["default_food"] == "focus"


def test_formal_catalog_uses_user_visibility_and_database_elfie_selection(
    client: TestClient,
    db_path: str,
    food_catalog_path: Path,
) -> None:
    owner_login = client.post(
        "/api/auth/login",
        data={"username": "owner", "password": "ownerchangeme"},
    )
    owner_csrf = owner_login.headers["X-CSRF-Token"]
    client.post(
        "/api/owner/users",
        json={"username": "alice", "password": "pass123", "role": "user"},
        headers=headers(owner_csrf),
    )
    user_login = client.post(
        "/api/auth/login",
        data={"username": "alice", "password": "pass123"},
    )
    user_csrf = user_login.headers["X-CSRF-Token"]
    adopted = client.post(
        "/api/user/adopt",
        json={
            "name": "小白",
            "anatomy_type": "biped",
            "personality_style": "好奇探索",
            "height": "standard",
            "build": "standard",
        },
        headers=headers(user_csrf),
    )
    elfie_id = adopted.json()["elfie_id"]
    with get_db(db_path) as connection:
        user_id = int(
            connection.execute(
                "SELECT id FROM users WHERE username = 'alice'"
            ).fetchone()[0]
        )
    recipes = {
        key: FoodRecipe(
            key,
            name,
            "",
            ExecutionProfile(f"ollama/{key}"),
            local_only=True,
        )
        for key, name in (
            ("food_000000000001", "默认粮"),
            ("food_000000000002", "保底粮"),
            ("food_000000000003", "用户粮"),
        )
    }
    FoodCatalogStore(food_catalog_path).save(
        FoodCatalog(
            default_food="food_000000000001",
            fallback_food="food_000000000002",
            recipes=recipes,
        )
    )
    owner_login = client.post(
        "/api/auth/login",
        data={"username": "owner", "password": "ownerchangeme"},
    )
    owner_csrf = owner_login.headers["X-CSRF-Token"]
    granted = client.put(
        "/api/owner/runtime/foods/food_000000000003/visibility",
        json={"user_ids": [user_id]},
        headers=headers(owner_csrf),
    )
    assert granted.status_code == 200, granted.text

    user_login = client.post(
        "/api/auth/login",
        data={"username": "alice", "password": "pass123"},
    )
    user_csrf = user_login.headers["X-CSRF-Token"]
    available = client.get(
        f"/api/user/elfies/{elfie_id}/food-policy/",
        headers=headers(user_csrf),
    ).json()
    assert available["allowed_foods"] == list(recipes)
    selected = client.put(
        f"/api/user/elfies/{elfie_id}/food-policy/",
        json={"default_food": "food_000000000003"},
        headers=headers(user_csrf),
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["default_food"] == "food_000000000003"
    with get_db(db_path) as connection:
        stored = connection.execute(
            """
            SELECT primary_food_key
            FROM elfie_food_preferences
            WHERE elfie_id = ?
            """,
            (elfie_id,),
        ).fetchone()
    assert stored["primary_food_key"] == "food_000000000003"
