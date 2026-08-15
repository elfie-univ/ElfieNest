"""Stable browser/native-client API contracts without legacy configuration leaks."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import create_app
from elfie.body import BodyId, BodySensorEvent, UtteranceFinal
from elfie.message_types import (
    ActorId,
    ActorRef,
    EventId,
)
from infrastructure.persistence.nest_db.store import init_db

from ._helpers import (
    adopt_test_elfie,
    complete_test_setup,
    create_test_owner,
    create_test_user,
)


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "nest.db")


@pytest.fixture
def client(tmp_path: Path, db_path: str, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    init_db(db_path)
    create_test_owner(db_path)
    application = create_app(engine=None, db_path=db_path)
    with TestClient(application, base_url="http://127.0.0.1:8000") as test_client:
        yield test_client


def _login_owner(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login", data={"account_id": "owner", "password": "ownerchangeme"}
    )
    assert response.status_code == 200
    return response.headers["X-CSRF-Token"]


def _adopt_elfie(client: TestClient, db_path: str, csrf_token: str) -> str:
    _ = csrf_token
    current_user = client.get("/api/v1/me")
    assert current_user.status_code == 200
    return adopt_test_elfie(
        db_path,
        int(current_user.json()["user_id"]),
    )


def _complete_setup(db_path: str) -> None:
    complete_test_setup(db_path)


def test_elfie_resources_are_registered_without_legacy_owner_route(
    client: TestClient,
    db_path: str,
) -> None:
    csrf_token = _login_owner(client)
    elfie_id = _adopt_elfie(client, db_path, csrf_token)

    member = client.get("/api/v1/elfies")
    profile = client.get(f"/api/v1/elfies/{elfie_id}/profile")
    admin = client.get("/api/v1/admin/elfies")
    legacy = client.get("/api/owner/elfies")

    assert member.status_code == 200
    assert member.json()["items"][0]["profile"]["elfie_id"] == elfie_id
    assert profile.status_code == 200
    assert profile.json()["profile"]["elfie_id"] == elfie_id
    assert admin.status_code == 200
    assert admin.json()["items"][0]["profile"]["elfie_id"] == elfie_id
    assert legacy.status_code == 404


def test_v1_routes_require_a_session(client: TestClient) -> None:
    assert client.get("/api/v1/me").status_code == 401
    assert client.get("/api/v1/elfies").status_code == 401


def test_v1_profile_is_public_but_messages_hide_another_users_elfie(
    client: TestClient, db_path: str
) -> None:
    owner_csrf = _login_owner(client)
    elfie_id = _adopt_elfie(client, db_path, owner_csrf)
    create_user = client.post(
        "/api/v1/admin/users",
        json={"account_id": "alice", "password": "pass123", "role": "user"},
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert create_user.status_code == 201
    client.cookies.clear()
    login = client.post(
        "/api/v1/auth/login", data={"account_id": "alice", "password": "pass123"}
    )
    assert login.status_code == 200

    profile = client.get(f"/api/v1/elfies/{elfie_id}/profile")
    messages = client.get(f"/api/v1/me/conversations/{elfie_id}/messages")

    assert profile.status_code == 200
    assert profile.json()["relationship"] == "other"
    assert profile.json()["private_cognition"] is None
    assert messages.status_code == 404


def test_owner_can_persist_a_safe_default_landing_page(
    client: TestClient, db_path: str
) -> None:
    csrf_token = _login_owner(client)
    _complete_setup(db_path)

    response = client.put(
        "/api/v1/me/default-landing-page",
        json={"default_landing_page": "chat"},
        headers={"X-CSRF-Token": csrf_token},
    )
    root = client.get("/", follow_redirects=False)

    assert response.status_code == 200
    assert response.json() == {"default_landing_page": "chat"}
    assert root.headers["location"] == "/chat"


def test_admin_can_persist_a_safe_default_landing_page(
    client: TestClient, db_path: str
) -> None:
    create_test_user(db_path, "admin", "admin-password", "admin")
    _complete_setup(db_path)
    login = client.post(
        "/api/v1/auth/login", data={"account_id": "admin", "password": "admin-password"}
    )
    assert login.status_code == 200

    response = client.put(
        "/api/v1/me/default-landing-page",
        json={"default_landing_page": "chat"},
        headers={"X-CSRF-Token": login.headers["X-CSRF-Token"]},
    )
    root = client.get("/", follow_redirects=False)

    assert response.status_code == 200
    assert response.json() == {"default_landing_page": "chat"}
    assert root.headers["location"] == "/chat"


def test_owner_can_enroll_rotate_and_revoke_a_hashed_body_credential(
    client: TestClient,
    db_path: str,
) -> None:
    csrf_token = _login_owner(client)
    elfie_id = _adopt_elfie(client, db_path, csrf_token)
    enrolled = client.post(
        f"/api/v1/elfies/{elfie_id}/bodies",
        json={"display_name": "客厅玩具", "body_type": "toy"},
        headers={"X-CSRF-Token": csrf_token},
    )
    body_id = enrolled.json()["body_id"]
    original_bearer = enrolled.json()["bearer_token"]
    rotated = client.post(
        f"/api/v1/elfies/{elfie_id}/bodies/{body_id}/credential-rotations",
        headers={"X-CSRF-Token": csrf_token},
    )
    revoked = client.delete(
        f"/api/v1/elfies/{elfie_id}/bodies/{body_id}",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert enrolled.status_code == 201
    assert original_bearer not in str(
        client.get(f"/api/v1/elfies/{elfie_id}/bodies").json()
    )
    assert rotated.status_code == 201
    assert rotated.json()["bearer_token"] != original_bearer
    assert revoked.status_code == 204


def test_body_websocket_routes_versioned_sensor_events_and_command_polls(
    client: TestClient,
    db_path: str,
) -> None:
    csrf_token = _login_owner(client)
    elfie_id = _adopt_elfie(client, db_path, csrf_token)
    enrolled = client.post(
        f"/api/v1/elfies/{elfie_id}/bodies",
        json={"display_name": "客厅玩具", "body_type": "toy"},
        headers={"X-CSRF-Token": csrf_token},
    )
    body_id = str(enrolled.json()["body_id"])
    bearer_token = str(enrolled.json()["bearer_token"])
    event = BodySensorEvent(
        event_id=EventId("device-sensor-1"),
        body_id=BodyId(body_id),
        source=ActorRef(actor_id=ActorId("device-owner"), source_kind="microphone"),
        occurred_at=datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc),
        received_at=datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc),
        payload=UtteranceFinal(kind="utterance_final", text="听见了吗？"),
    )
    with client.websocket_connect(
        "/api/v1/ws/bodies",
        headers={"Authorization": f"Bearer {bearer_token}"},
    ) as websocket:
        ready = websocket.receive_json()
        assert ready["protocol_version"] == "1"
        assert ready["event"] == "ready"
        assert ready["payload"] == {"body_id": body_id}
        websocket.send_json(
            {
                "protocol_version": "1",
                "event_id": "sensor-frame-1",
                "occurred_at": "2026-07-24T08:00:00Z",
                "event": "sensor_event",
                "sensor_event": event.model_dump(mode="json"),
            }
        )
        sensor_result = websocket.receive_json()
        assert sensor_result["event"] == "sensor_event"
        assert sensor_result["payload"] == {"delivered": False}
        websocket.send_json(
            {
                "protocol_version": "1",
                "event_id": "poll-frame-1",
                "occurred_at": "2026-07-24T08:00:00Z",
                "event": "command_poll",
            }
        )
        command_batch = websocket.receive_json()

    assert command_batch["event"] == "commands"
    assert command_batch["payload"] == {"commands": []}


def test_v1_session_projection_includes_the_owner_landing_preference(
    client: TestClient,
) -> None:
    _login_owner(client)

    response = client.get("/api/v1/me")

    assert response.status_code == 200
    assert response.json()["default_landing_page"] == "manage"


def test_v1_openapi_route_snapshot(client: TestClient) -> None:
    paths = client.app.openapi()["paths"]

    assert {
        "/api/v1/me",
        "/api/v1/me/default-landing-page",
        "/api/v1/elfies",
        "/api/v1/elfies/{elfie_id}/profile",
        "/api/v1/elfies/{elfie_id}/bodies",
        "/api/v1/elfies/{elfie_id}/bodies/{body_id}",
        "/api/v1/elfies/{elfie_id}/bodies/{body_id}/credential-rotations",
        "/api/v1/me/conversations",
        "/api/v1/me/conversations/{elfie_id}/messages",
    } <= set(paths)
    assert "/api/v1/owner/devices" not in paths
