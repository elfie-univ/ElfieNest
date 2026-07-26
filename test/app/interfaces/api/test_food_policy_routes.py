from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.persistence.store import init_db
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
