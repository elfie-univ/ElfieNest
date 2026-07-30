"""Owner monitoring API contract tests for safe Elfie projections."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.devices import DeviceRegistry
from app.infrastructure.persistence.embodiment_sessions import begin_hosting
from app.infrastructure.persistence.store import init_db
from app.interfaces.api.app import create_app

from ._helpers import create_test_owner


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Create a session-isolated API client with an Owner account."""
    db_path = str(tmp_path / "nest.db")
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path / "elfienest-home"))
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


def _login(client: TestClient, username: str, password: str) -> dict:
    response = client.post(
        "/api/auth/login", data={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return {
        "csrf_token": response.headers["X-CSRF-Token"],
        "user_id": response.json()["user"]["id"],
    }


def _adopt_elfie(
    client: TestClient, csrf_token: str, name: str, species_id: str
) -> str:
    response = client.post(
        "/api/user/adopt",
        json={
            "name": name,
            "species_id": species_id,
            "personality_style": "好奇探索",
            "height": "standard",
            "build": "standard",
        },
        headers=_headers(csrf_token),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["elfie_id"])


@pytest.fixture
def monitoring_world(client: TestClient) -> dict:
    """Seed three Elfies whose owner, species, food and state all differ."""
    owner = _login(client, "owner", "ownerchangeme")
    for username, password in (("alice", "alice-pass"), ("bob", "bob-pass")):
        response = client.post(
            "/api/owner/users",
            json={"username": username, "password": password, "role": "user"},
            headers=_headers(str(owner["csrf_token"])),
        )
        assert response.status_code == 201, response.text

    alice = _login(client, "alice", "alice-pass")
    alice_dog = _adopt_elfie(client, str(alice["csrf_token"]), "星尘", "dog")
    alice_fox = _adopt_elfie(client, str(alice["csrf_token"]), "月光", "fox")
    policy = client.put(
        f"/api/user/elfies/{alice_dog}/food-policy/",
        json={
            "default_food": "focus",
            "allowed_foods": ["coarse", "focus"],
            "fallback_food": "coarse",
        },
        headers=_headers(str(alice["csrf_token"])),
    )
    assert policy.status_code == 200, policy.text
    body = DeviceRegistry(client.app.state.db_path).enroll(
        alice_dog, "Test Body", "toy"
    )
    begin_hosting(client.app.state.db_path, alice_dog, body.body_id, lease_seconds=30)

    bob = _login(client, "bob", "bob-pass")
    bob_dog = _adopt_elfie(client, str(bob["csrf_token"]), "晨星", "dog")

    return {
        "owner": _login(client, "owner", "ownerchangeme"),
        "alice": alice,
        "bob": bob,
        "alice_dog": alice_dog,
        "alice_fox": alice_fox,
        "bob_dog": bob_dog,
    }


def test_owner_elfie_monitoring_projection_is_safe_and_structured(
    client: TestClient, monitoring_world: dict
) -> None:
    # Given: an Owner and a hosted Elfie with an explicit food policy.
    owner = monitoring_world["owner"]

    # When: the Owner loads the unfiltered monitoring list.
    response = client.get(
        "/api/owner/elfies", headers=_headers(str(owner["csrf_token"]))
    )

    # Then: the row is a public monitoring projection without configuration or history leaks.
    assert response.status_code == 200, response.text
    row = next(
        item
        for item in response.json()
        if item["elfie_id"] == monitoring_world["alice_dog"]
    )
    assert set(row) == {"elfie_id", "owner", "profile", "food_policy", "created_at"}
    assert row["owner"] == {
        "user_id": monitoring_world["alice"]["user_id"],
        "username": "alice",
    }
    assert set(row["profile"]) == {
        "elfie_id",
        "name",
        "species_id",
        "gender",
        "birth_date",
        "summary",
        "online_status",
        "portrait_url",
        "appearance",
        "big_five",
        "personality_tags",
        "nest",
        "embodiment",
    }
    assert row["profile"]["name"] == "星尘"
    assert row["profile"]["species_id"] == "dog"
    assert row["profile"]["gender"] is None
    assert row["profile"]["birth_date"] is None
    assert row["profile"]["summary"]
    assert row["profile"]["online_status"] == "unknown"
    assert row["profile"]["embodiment"] == {"state": "switching_to_hosted"}
    assert row["food_policy"] == {
        "default_food": "focus",
        "allowed_foods": ["coarse", "focus"],
        "fallback_food": "coarse",
    }
    rendered = str(row)
    for forbidden in (
        "config_dir",
        "configs",
        "profile.yaml",
        "personality.yaml",
        "capabilities.yaml",
        "system_limits.yaml",
        "chat_history",
        "secret",
    ):
        assert forbidden not in rendered


@pytest.mark.parametrize(
    ("filter_key", "filter_value", "expected_key"),
    [
        ("owner_user_id", "alice_user_id", "alice"),
        ("species_id", "dog", "dogs"),
        ("food_key", "focus", "alice_dog"),
        ("embodiment_state", "switching_to_hosted", "alice_dog"),
        ("owner_user_id", "999999", "none"),
    ],
)
def test_owner_elfie_monitoring_filters_rows(
    client: TestClient,
    monitoring_world: dict,
    filter_key: str,
    filter_value: str,
    expected_key: str,
) -> None:
    # Given: a monitoring list with distinct owners, species, food policies and states.
    owner = monitoring_world["owner"]
    expected_ids = {
        "alice": {monitoring_world["alice_dog"], monitoring_world["alice_fox"]},
        "dogs": {monitoring_world["alice_dog"], monitoring_world["bob_dog"]},
        "alice_dog": {monitoring_world["alice_dog"]},
        "none": set(),
    }[expected_key]
    query_value = (
        str(monitoring_world["alice"]["user_id"])
        if filter_value == "alice_user_id"
        else filter_value
    )

    # When: the Owner supplies one monitoring filter.
    response = client.get(
        "/api/owner/elfies",
        params={filter_key: query_value},
        headers=_headers(str(owner["csrf_token"])),
    )

    # Then: only matching public projection rows are returned.
    assert response.status_code == 200, response.text
    assert {row["elfie_id"] for row in response.json()} == expected_ids


def test_user_cannot_read_owner_elfie_monitoring(
    client: TestClient, monitoring_world: dict
) -> None:
    # Given: a normal authenticated user.
    _ = monitoring_world
    alice = _login(client, "alice", "alice-pass")

    # When: the user requests the Owner monitoring endpoint.
    response = client.get(
        "/api/owner/elfies", headers=_headers(str(alice["csrf_token"]))
    )

    # Then: Owner-only monitoring is denied.
    assert response.status_code == 403


def test_user_elfie_detail_hides_raw_configuration(
    client: TestClient, monitoring_world: dict
) -> None:
    # Given: an authenticated owner of one Elfie.
    alice = _login(client, "alice", "alice-pass")
    elfie_id = monitoring_world["alice_dog"]

    # When: the user reads the detail.
    detail = client.get(
        f"/api/user/elfies/{elfie_id}", headers=_headers(str(alice["csrf_token"]))
    )

    # Then: the read contains no raw filesystem or YAML fields.
    assert detail.status_code == 200, detail.text
    assert "config_dir" not in detail.json()
    assert "configs" not in detail.json()


def test_user_elfie_config_write_route_is_gone(
    client: TestClient, monitoring_world: dict
) -> None:
    # Given: an authenticated owner of one Elfie.
    alice = _login(client, "alice", "alice-pass")
    elfie_id = monitoring_world["alice_dog"]

    # When: the user attempts the retired generic YAML write route.
    response = client.put(
        f"/api/user/elfies/{elfie_id}/config",
        json={"filename": "personality.yaml", "content": "big_five: {}"},
        headers=_headers(str(alice["csrf_token"])),
    )

    # Then: raw YAML mutation is no longer available.
    assert response.status_code in {404, 410}


def test_food_policy_is_structured_for_the_owner(
    client: TestClient, monitoring_world: dict
) -> None:
    # Given: Alice owns an Elfie with an explicit structured food policy.
    alice = _login(client, "alice", "alice-pass")
    elfie_id = monitoring_world["alice_dog"]

    # When: Alice reads the policy.
    response = client.get(
        f"/api/user/elfies/{elfie_id}/food-policy/",
        headers=_headers(str(alice["csrf_token"])),
    )

    # Then: the owner receives the structured policy.
    assert response.status_code == 200, response.text
    assert response.json() == {
        "elfie_id": elfie_id,
        "default_food": "focus",
        "allowed_foods": ["coarse", "focus"],
        "fallback_food": "coarse",
    }


def test_food_policy_hides_another_users_elfie(
    client: TestClient, monitoring_world: dict
) -> None:
    # Given: Bob does not own Alice's Elfie.
    bob = _login(client, "bob", "bob-pass")
    elfie_id = monitoring_world["alice_dog"]

    # When: Bob reads Alice's structured food policy.
    response = client.get(
        f"/api/user/elfies/{elfie_id}/food-policy/",
        headers=_headers(str(bob["csrf_token"])),
    )

    # Then: the target is hidden from another user.
    assert response.status_code == 404


def test_owner_monitoring_treats_empty_filter_values_as_all(
    client: TestClient, monitoring_world: dict
) -> None:
    owner = _login(client, "owner", "ownerchangeme")

    response = client.get(
        "/api/owner/elfies?owner_user_id=&species_id=&food_key=&status=",
        headers=_headers(str(owner["csrf_token"])),
    )

    assert response.status_code == 200
    assert len(response.json()) == 3
