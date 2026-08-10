"""Live Settings-to-Adoption policy projection tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import create_app
from infrastructure.persistence.store import init_db

from ._helpers import adopt_test_elfie, create_test_owner


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_test_owner(db_path)
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        with TestClient(application) as test_client:
            yield test_client


def _headers(csrf_token: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf_token, "Content-Type": "application/json"}


def _login_owner(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        data={"account_id": "owner", "password": "ownerchangeme"},
    )
    assert response.status_code == 200
    return response.headers["X-CSRF-Token"]


def _create_user_and_login(client: TestClient) -> tuple[int, str]:
    owner_csrf = _login_owner(client)
    created = client.post(
        "/api/v1/admin/users",
        json={"account_id": "alice", "password": "pass123", "role": "user"},
        headers=_headers(owner_csrf),
    )
    assert created.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        data={"account_id": "alice", "password": "pass123"},
    )
    assert login.status_code == 200
    return int(created.json()["user_id"]), login.headers["X-CSRF-Token"]


def test_adoption_options_reflect_settings_filters(client: TestClient) -> None:
    owner_csrf = _login_owner(client)
    updated = client.patch(
        "/api/v1/admin/settings/elfies",
        json={
            "allowed_species_ids": ["dog"],
            "personality_presets_enabled": {"安静温顺": False},
        },
        headers=_headers(owner_csrf),
    )
    assert updated.status_code == 200
    _user_id, user_csrf = _create_user_and_login(client)

    response = client.get(
        "/api/v1/me/adoption",
        headers=_headers(user_csrf),
    )

    assert response.status_code == 200
    assert response.json()["species_ids"] == ["dog"]
    assert "安静温顺" not in response.json()["personality_styles"]


def test_adoption_options_use_live_quota(client: TestClient) -> None:
    owner_csrf = _login_owner(client)
    updated = client.patch(
        "/api/v1/admin/settings/elfies",
        json={"max_elfies_per_user": 1},
        headers=_headers(owner_csrf),
    )
    assert updated.status_code == 200
    user_id, user_csrf = _create_user_and_login(client)
    adopt_test_elfie(client.app.state.db_path, user_id)

    response = client.get(
        "/api/v1/me/adoption",
        headers=_headers(user_csrf),
    )

    assert response.status_code == 200
    assert response.json()["quota"] == {
        "used": 1,
        "max": 1,
        "remaining": 0,
        "can_adopt": False,
    }


def test_all_disabled_personalities_keep_existing_safe_fallback(
    client: TestClient,
) -> None:
    owner_csrf = _login_owner(client)
    updated = client.patch(
        "/api/v1/admin/settings/elfies",
        json={
            "personality_presets_enabled": {
                "活泼好动": False,
                "安静温顺": False,
                "好奇探索": False,
                "胆小害羞": False,
                "傲娇独立": False,
                "完全随机": False,
            }
        },
        headers=_headers(owner_csrf),
    )
    assert updated.status_code == 200
    _user_id, user_csrf = _create_user_and_login(client)

    response = client.get(
        "/api/v1/me/adoption",
        headers=_headers(user_csrf),
    )

    assert response.status_code == 200
    assert len(response.json()["personality_styles"]) == 6
