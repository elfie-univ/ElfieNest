from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.persistence.store import get_db, init_db
from app.interfaces.api.app import create_app
from nest.godot_gateway.observer import WorldChangingIntent

from ._helpers import create_test_owner, create_test_user


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "observer.db")


@pytest.fixture
def client(db_path: str) -> TestClient:
    init_db(db_path)
    create_test_owner(db_path)
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=19876)
        with TestClient(application) as test_client:
            yield test_client


def test_observer_intent_requires_authenticated_owner_or_elfie_family(
    client: TestClient,
    db_path: str,
) -> None:
    # Given: Alice owns an Elfie and the app has one observable world-intent sink.
    alice_id = create_test_user(db_path, "alice", "alice-password")
    create_test_user(db_path, "bob", "bob-password")
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT INTO elfie_registry (elfie_id, name, owner_user_id) VALUES (?, ?, ?)",
            ("fox-1", "Fox", alice_id),
        )
        connection.commit()
    observed: list[WorldChangingIntent] = []
    client.app.state.observer_intent_sink = observed.append
    alice_csrf = _login(client, "alice", "alice-password")
    capability = _open_elfie_observer(client, alice_csrf, "fox-1")

    # When: Alice sends one typed high-level interaction through her capability.
    accepted = client.post(
        "/api/observer/intents",
        json={
            "kind": "request_interaction",
            "actor_id": "fox-1",
            "interaction": "greet",
        },
        headers=_headers(alice_csrf, capability),
    )
    bob_csrf = _login(client, "bob", "bob-password")
    rejected = client.post(
        "/api/observer/intents",
        json={
            "kind": "request_interaction",
            "actor_id": "fox-1",
            "interaction": "greet",
        },
        headers=_headers(bob_csrf, capability),
    )

    # Then: session identity gates the world-changing request before sink mutation.
    assert accepted.status_code == 202
    assert rejected.status_code == 403
    assert observed == [
        WorldChangingIntent(
            kind="request_interaction",
            actor_id="fox-1",
            interaction="greet",
        )
    ]


def test_observer_route_rejects_authority_nonce_and_coordinate_payload(
    client: TestClient,
    db_path: str,
) -> None:
    # Given: an authenticated Owner has a regular Observer session.
    create_test_user(db_path, "alice", "alice-password")
    csrf_token = _login(client, "owner", "ownerchangeme")

    # When: the request tries to use an authority nonce or coordinate write.
    nonce_response = client.post(
        "/api/observer/sessions",
        json={
            "protocol": 3,
            "role": "observer",
            "subscription": {"kind": "room", "room_id": "local-nest"},
            "nonce": "stolen-authority-nonce",
        },
        headers=_headers(csrf_token),
    )
    capability = _open_room_observer(client, csrf_token)
    coordinates_response = client.post(
        "/api/observer/intents",
        json={
            "kind": "request_interaction",
            "actor_id": "fox-1",
            "interaction": "greet",
            "transform": {"x": 1},
        },
        headers=_headers(csrf_token, capability),
    )

    # Then: neither authority credentials nor geometry reach the world sink.
    assert nonce_response.status_code == 422
    assert coordinates_response.status_code == 422


def test_observer_capability_rejects_new_same_user_session_and_logout_replay(
    client: TestClient,
    db_path: str,
) -> None:
    # Given: Alice creates a capability through her first authenticated session.
    alice_id = create_test_user(db_path, "alice", "alice-password")
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT INTO elfie_registry (elfie_id, name, owner_user_id) VALUES (?, ?, ?)",
            ("fox-1", "Fox", alice_id),
        )
        connection.commit()
    observed: list[WorldChangingIntent] = []
    client.app.state.observer_intent_sink = observed.append
    first_csrf = _login(client, "alice", "alice-password")
    capability = _open_elfie_observer(client, first_csrf, "fox-1")

    # When: Alice logs out and signs in again, then replays the old capability.
    logout = client.post("/api/auth/logout", headers=_headers(first_csrf))
    second_csrf = _login(client, "alice", "alice-password")
    replay = client.post(
        "/api/observer/intents",
        json={
            "kind": "request_interaction",
            "actor_id": "fox-1",
            "interaction": "greet",
        },
        headers=_headers(second_csrf, capability),
    )

    # Then: same principal, different session is denied and cannot mutate the sink.
    assert logout.status_code == 200
    assert replay.status_code == 403
    assert observed == []


def test_observer_session_requires_csrf_and_rejects_nested_capability_fields(
    client: TestClient,
) -> None:
    # Given: a valid Owner session exists.
    csrf_token = _login(client, "owner", "ownerchangeme")
    payload = {
        "protocol": 3,
        "role": "observer",
        "subscription": {
            "kind": "room",
            "room_id": "local-nest",
            "capability": "nested-secret",
        },
    }

    # When: session creation omits CSRF or smuggles a nested capability.
    no_csrf = client.post("/api/observer/sessions", json=payload)
    nested_capability = client.post(
        "/api/observer/sessions",
        json=payload,
        headers=_headers(csrf_token),
    )

    # Then: both requests stop before observer capability issuance.
    assert no_csrf.status_code == 403
    assert nested_capability.status_code == 422


def test_observer_frame_route_projects_semantics_and_resyncs_stale_cursor(
    client: TestClient,
) -> None:
    # Given: an authenticated Owner has a room capability and semantic source only.
    csrf_token = _login(client, "owner", "ownerchangeme")
    entities = {
        "fox-1": {
            "room_id": "local-nest",
            "zone_id": None,
            "posture": "awake",
            "active": True,
            "active_command_id": None,
        }
    }
    client.app.state.observer_semantic_entities = lambda: entities
    capability = _open_room_observer(client, csrf_token)

    # When: it reads a snapshot, advances state once, then reuses a stale cursor.
    initial = client.get(
        "/api/observer/frames",
        headers=_headers(csrf_token, capability),
    )
    initial_body = initial.json()
    entities["fox-1"] = {
        "room_id": "local-nest",
        "zone_id": "dorm",
        "posture": "resting",
        "active": True,
        "active_command_id": "intent-7",
    }
    delta = client.get(
        "/api/observer/frames",
        params={
            "acknowledged_generation": initial_body["generation"],
            "acknowledged_sequence": initial_body["sequence"],
        },
        headers=_headers(csrf_token, capability),
    )
    entities["fox-1"] = {
        "room_id": "local-nest",
        "zone_id": None,
        "posture": "resting",
        "active": True,
        "active_command_id": None,
    }
    cleared = client.get(
        "/api/observer/frames",
        params={
            "acknowledged_generation": delta.json()["generation"],
            "acknowledged_sequence": delta.json()["sequence"],
        },
        headers=_headers(csrf_token, capability),
    )
    entities["fox-1"] = {
        "room_id": "local-nest",
        "zone_id": None,
        "posture": "sleeping",
        "active": True,
        "active_command_id": None,
    }
    resync = client.get(
        "/api/observer/frames",
        params={
            "acknowledged_generation": initial_body["generation"],
            "acknowledged_sequence": initial_body["sequence"],
        },
        headers=_headers(csrf_token, capability),
    )

    # Then: Python exposes semantic fields, a real delta, and a safe snapshot resync.
    assert initial.status_code == 200
    assert initial_body["kind"] == "snapshot"
    assert "coordinates" not in initial_body["entities"]["fox-1"]
    assert initial_body["entities"]["fox-1"]["zone_id"] is None
    assert initial_body["entities"]["fox-1"]["active_command_id"] is None
    assert delta.status_code == 200
    assert delta.json()["kind"] == "delta"
    assert delta.json()["patch"] == {
        "zone_id": "dorm",
        "posture": "resting",
        "active_command_id": "intent-7",
    }
    assert cleared.status_code == 200
    assert cleared.json()["kind"] == "delta"
    assert cleared.json()["patch"] == {
        "zone_id": None,
        "active_command_id": None,
    }
    assert resync.status_code == 200
    assert resync.json()["kind"] == "snapshot"
    assert resync.json()["entities"]["fox-1"]["posture"] == "sleeping"


def test_interest_cannot_widen_an_existing_elfie_capability(
    client: TestClient,
    db_path: str,
) -> None:
    # Given: Alice owns Fox but not Owl, and holds an Elfie-only capability.
    alice_id = create_test_user(db_path, "alice", "alice-password")
    with get_db(db_path) as connection:
        connection.executemany(
            "INSERT INTO elfie_registry (elfie_id, name, owner_user_id) VALUES (?, ?, ?)",
            [("fox-1", "Fox", alice_id), ("owl-1", "Owl", 1)],
        )
        connection.commit()
    csrf_token = _login(client, "alice", "alice-password")
    capability = _open_elfie_observer(client, csrf_token, "fox-1")

    # When: the capability tries to replace its exact scope with the whole room.
    widened = client.put(
        "/api/observer/interest",
        json={
            "subscription": {"kind": "room", "room_id": "local-nest"},
            "visible_entity_ids": ["fox-1", "owl-1"],
        },
        headers=_headers(csrf_token, capability),
    )

    # Then: scope escalation is rejected; callers must open a new capability.
    assert widened.status_code == 403


def test_observer_frames_require_live_authenticated_session(client: TestClient) -> None:
    # Given: no browser login or observer capability exists.

    # When: a caller tries to poll a projection endpoint.
    response = client.get(
        "/api/observer/frames",
        headers={"X-ElfieNest-Observer-Capability": "observer_replay"},
    )

    # Then: the API never reveals a projection to an anonymous caller.
    assert response.status_code == 401


def _login(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/api/auth/login", data={"username": username, "password": password}
    )
    assert response.status_code == 200
    return response.headers["X-CSRF-Token"]


def _open_elfie_observer(client: TestClient, csrf_token: str, elfie_id: str) -> str:
    response = client.post(
        "/api/observer/sessions",
        json={
            "protocol": 3,
            "role": "observer",
            "subscription": {"kind": "elfie", "elfie_id": elfie_id},
        },
        headers=_headers(csrf_token),
    )
    assert response.status_code == 201
    return str(response.json()["capability"])


def _open_room_observer(client: TestClient, csrf_token: str) -> str:
    response = client.post(
        "/api/observer/sessions",
        json={
            "protocol": 3,
            "role": "observer",
            "subscription": {"kind": "room", "room_id": "local-nest"},
        },
        headers=_headers(csrf_token),
    )
    assert response.status_code == 201
    return str(response.json()["capability"])


def _headers(csrf_token: str, capability: str | None = None) -> dict[str, str]:
    headers = {"X-CSRF-Token": csrf_token, "Content-Type": "application/json"}
    if capability is not None:
        headers["X-ElfieNest-Observer-Capability"] = capability
    return headers
