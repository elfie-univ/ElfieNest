"""Stable browser/native-client API contracts without legacy configuration leaks."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ai_runtime.storage.data_home import get_elfie_conversations_dir
from ai_runtime.storage.data_layout import final_root_layout
from app.bootstrap import create_app
from app.infrastructure.devices import DeviceRegistry
from app.infrastructure.persistence.elfie_chat_history import (
    ElfieChatMessageInput,
    ElfieChatSender,
    record_elfie_chat_message,
)
from app.infrastructure.persistence.embodiment_sessions import begin_hosting
from app.infrastructure.persistence.store import init_db
from elfie import Elfie
from elfie.body import BodyId, BodySensorEvent, SpeechCommand, UtteranceFinal
from elfie.brain.memory.knowledge_store import KnowledgeStore
from elfie.brain.memory.node_types import MemoryNode
from elfie.communication.contracts import InboundDisposition, InboundDispositionStatus
from elfie.message_types import (
    ActorId,
    ActorRef,
    CommandId,
    ErrorInfo,
    EventId,
    IntentId,
    TurnId,
)

from ._helpers import (
    adopt_test_elfie,
    complete_test_setup,
    create_test_owner,
    create_test_user,
)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = str(tmp_path / "nest.db")
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    init_db(db_path)
    create_test_owner(db_path)
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        with TestClient(application, base_url="http://127.0.0.1:8000") as test_client:
            yield test_client


def _login_owner(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login", data={"account_id": "owner", "password": "ownerchangeme"}
    )
    assert response.status_code == 200
    return response.headers["X-CSRF-Token"]


def _adopt_elfie(client: TestClient, csrf_token: str) -> str:
    _ = csrf_token
    current_user = client.get("/api/v1/me")
    assert current_user.status_code == 200
    return adopt_test_elfie(
        client.app.state.db_path,
        int(current_user.json()["user_id"]),
    )


def _accepted_candidate(client: TestClient, csrf_token: str) -> tuple[str, str]:
    headers = {"X-CSRF-Token": csrf_token}
    candidates = client.post(
        "/api/user/adoption/candidates",
        json={
            "species_id": "fox",
            "life_stage": "young_adult",
            "gender": "any",
            "appearance": {
                "stature": "standard",
                "build": "standard",
                "face": "soft",
                "signature": "warm",
                "priority": "face",
            },
            "answers": ["quiet", "research", "plan", "discuss", "steady"],
        },
        headers=headers,
    ).json()
    selected_ids = [item["candidate_id"] for item in candidates["candidates"][:2]]
    replies = client.post(
        "/api/user/adoption/replies",
        json={
            "candidate_set_id": candidates["candidate_set_id"],
            "candidate_ids": selected_ids,
        },
        headers=headers,
    ).json()["replies"]
    accepted = next(reply for reply in replies if reply["status"] == "accepted")
    return str(candidates["candidate_set_id"]), str(accepted["candidate_id"])


def _complete_setup(client: TestClient) -> None:
    complete_test_setup(client.app.state.db_path)


def test_v1_profile_detail_exposes_private_projection_only_to_the_owner(
    client: TestClient,
) -> None:
    csrf_token = _login_owner(client)
    elfie_id = _adopt_elfie(client, csrf_token)

    response = client.get(f"/api/v1/elfies/{elfie_id}/profile")

    assert response.status_code == 200
    profile = response.json()
    assert profile["elfie_id"] == elfie_id
    assert profile["name"] == "小白"
    public_keys = {
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
    assert set(profile) == public_keys | {"private_cognition", "care_settings"}
    assert profile["private_cognition"]["status"] == "empty"
    assert set(profile["care_settings"]) == {"food"}
    assert set(profile["care_settings"]["food"]) == {
        "selected_id",
        "selected_label",
        "options",
        "unavailable",
    }
    listing = client.get("/api/v1/elfies")
    assert listing.status_code == 200
    assert set(listing.json()[0]) == public_keys
    rendered = str(profile)
    assert "config_dir" not in rendered
    assert "profile.yaml" not in rendered
    assert "memory" not in rendered


def test_v1_owner_profile_reads_real_cognition_but_list_stays_public(
    client: TestClient,
) -> None:
    csrf_token = _login_owner(client)
    elfie_id = _adopt_elfie(client, csrf_token)
    data_home = Path(client.app.state.db_path).parent
    cognition_path = final_root_layout(data_home).elfie(elfie_id).knowledge_database
    cognition_path.parent.mkdir(parents=True)
    with KnowledgeStore(cognition_path) as store:
        store.add_node(
            MemoryNode(
                id="event_adoption",
                type="episodic",
                content="被主人领养，搬进了新的家。",
                metadata={
                    "timestamp": "2026-06-30T08:00:00Z",
                    "major_event": True,
                    "importance": 0.95,
                    "title": "被领养",
                },
            )
        )

    detail = client.get(f"/api/v1/elfies/{elfie_id}/profile")
    listing = client.get("/api/v1/elfies")

    assert detail.status_code == 200
    assert detail.json()["private_cognition"]["status"] == "ready"
    assert (
        detail.json()["private_cognition"]["important_experiences"]["entries"][0]["id"]
        == "event_adoption"
    )
    assert "private_cognition" not in listing.json()[0]
    assert "care_settings" not in listing.json()[0]


def test_v1_conversations_and_messages_are_owner_scoped(client: TestClient) -> None:
    csrf_token = _login_owner(client)
    elfie_id = _adopt_elfie(client, csrf_token)
    user_id = int(client.get("/api/v1/me").json()["user_id"])
    record_elfie_chat_message(
        elfie_id,
        ElfieChatMessageInput(
            message_id="v1-history-1",
            conversation_id=f"owner:{user_id}",
            user_id=user_id,
            sender=ElfieChatSender.USER,
            text="今天好吗？",
            channel="web",
            created_at="2026-07-24T08:00:00.000Z",
        ),
    )

    conversations = client.get("/api/v1/conversations")
    messages = client.get(f"/api/v1/conversations/{elfie_id}/messages")

    assert conversations.status_code == 200
    assert conversations.json()[0]["elfie_id"] == elfie_id
    assert conversations.json()[0]["last_message_preview"] == "今天好吗？"
    assert messages.status_code == 200
    assert messages.json()[0]["text"] == "今天好吗？"
    assert "meta" not in messages.json()[0]


def test_v1_writes_only_to_the_owned_elfie_workspace(client: TestClient) -> None:
    csrf_token = _login_owner(client)
    elfie_id = _adopt_elfie(client, csrf_token)

    response = client.post(
        f"/api/v1/conversations/{elfie_id}/messages",
        json={"text": "只应存在于精灵工作区"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    history_path = get_elfie_conversations_dir(elfie_id) / "history.sqlite"
    assert history_path.exists()
    with sqlite3.connect(client.app.state.db_path) as connection:
        legacy_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'chat_messages'"
        ).fetchone()
    assert legacy_table is None


def test_v1_can_send_an_owned_message_without_exposing_legacy_meta(
    client: TestClient,
) -> None:
    csrf_token = _login_owner(client)
    elfie_id = _adopt_elfie(client, csrf_token)

    response = client.post(
        f"/api/v1/conversations/{elfie_id}/messages",
        json={"text": "你好，小白"},
        headers={"X-CSRF-Token": csrf_token},
    )
    messages = client.get(f"/api/v1/conversations/{elfie_id}/messages")

    assert response.status_code == 200
    assert response.json()["text"] == "你好，小白"
    assert "meta" not in response.json()
    assert [message["text"] for message in messages.json()] == ["你好，小白"]


def test_v1_chat_does_not_ack_or_persist_when_runtime_does_not_admit_message(
    client: TestClient,
) -> None:
    csrf_token = _login_owner(client)
    elfie_id = _adopt_elfie(client, csrf_token)
    session_token = client.cookies.get("session_token")
    assert session_token

    unavailable_engine = MagicMock()
    unavailable_engine.session.send_user_message.return_value = None
    client.app.state.engine = unavailable_engine

    response = client.post(
        f"/api/v1/conversations/{elfie_id}/messages",
        json={"text": "精灵听得到吗？"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "elfie_runtime_unavailable"

    with client.websocket_connect(
        "/api/v1/ws/chat", headers={"Cookie": f"session_token={session_token}"}
    ) as websocket:
        assert websocket.receive_json()["event"] == "ready"
        websocket.send_json(
            {"event": "user_message", "elfie_id": elfie_id, "text": "再试一次"}
        )
        assert websocket.receive_json() == {
            "event": "error",
            "detail": "elfie_runtime_unavailable",
        }

    messages = client.get(f"/api/v1/conversations/{elfie_id}/messages")
    assert messages.json() == []


def test_v1_chat_does_not_ack_or_persist_duplicate_message(
    client: TestClient,
) -> None:
    csrf_token = _login_owner(client)
    elfie_id = _adopt_elfie(client, csrf_token)
    runtime = MagicMock()
    runtime.session.send_user_message.return_value = InboundDisposition(
        message_id=EventId("duplicate-message"),
        channel_id="godot-owner",
        status=InboundDispositionStatus.DUPLICATE,
    )
    client.app.state.engine = runtime

    response = client.post(
        f"/api/v1/conversations/{elfie_id}/messages",
        json={"text": "重复消息"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "duplicate_message"
    assert client.get(f"/api/v1/conversations/{elfie_id}/messages").json() == []


@pytest.mark.parametrize(
    ("retryable", "expected_status"),
    [(True, 503), (False, 409)],
)
def test_v1_chat_maps_rejected_message_to_retryable_status(
    client: TestClient,
    retryable: bool,
    expected_status: int,
) -> None:
    csrf_token = _login_owner(client)
    elfie_id = _adopt_elfie(client, csrf_token)
    runtime = MagicMock()
    runtime.session.send_user_message.return_value = InboundDisposition(
        message_id=EventId("rejected-message"),
        channel_id="godot-owner",
        status=InboundDispositionStatus.REJECTED,
        error=ErrorInfo(
            code="transport_timeout",
            message="运行时超时",
            retryable=retryable,
        ),
    )
    client.app.state.engine = runtime

    response = client.post(
        f"/api/v1/conversations/{elfie_id}/messages",
        json={"text": "重试消息"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == expected_status
    assert response.json()["detail"] == "transport_timeout"
    assert client.get(f"/api/v1/conversations/{elfie_id}/messages").json() == []


def test_adoption_returns_service_unavailable_when_runtime_registration_fails(
    client: TestClient,
) -> None:
    csrf_token = _login_owner(client)
    candidate_set_id, candidate_id = _accepted_candidate(client, csrf_token)
    runtime = MagicMock()
    runtime.api_server = None
    runtime.session.register_elfie.side_effect = RuntimeError("runtime unavailable")
    client.app.state.engine = runtime

    with patch("elfie.ElfieFactory.restore", return_value=MagicMock(spec=Elfie)):
        response = client.post(
            "/api/user/adoption/commit",
            json={
                "candidate_set_id": candidate_set_id,
                "candidate_id": candidate_id,
                "name": "小白",
            },
            headers={"X-CSRF-Token": csrf_token},
        )

    assert response.status_code == 503
    assert client.get("/api/v1/elfies").json() == []


def test_v1_routes_require_a_session(client: TestClient) -> None:
    assert client.get("/api/v1/me").status_code == 401
    assert client.get("/api/v1/elfies").status_code == 401


def test_v1_profile_and_messages_hide_another_users_elfie(client: TestClient) -> None:
    owner_csrf = _login_owner(client)
    elfie_id = _adopt_elfie(client, owner_csrf)
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
    messages = client.get(f"/api/v1/conversations/{elfie_id}/messages")

    assert profile.status_code == 404
    assert messages.status_code == 404


def test_owner_can_persist_a_safe_default_landing_page(client: TestClient) -> None:
    csrf_token = _login_owner(client)
    _complete_setup(client)

    response = client.put(
        "/api/v1/me/default-landing-page",
        json={"default_landing_page": "chat"},
        headers={"X-CSRF-Token": csrf_token},
    )
    root = client.get("/", follow_redirects=False)

    assert response.status_code == 200
    assert response.json() == {"default_landing_page": "chat"}
    assert root.headers["location"] == "/chat"


def test_admin_can_persist_a_safe_default_landing_page(client: TestClient) -> None:
    create_test_user(client.app.state.db_path, "admin", "admin-password", "admin")
    _complete_setup(client)
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


def test_v1_profile_reads_the_persisted_embodiment_state(client: TestClient) -> None:
    csrf_token = _login_owner(client)
    elfie_id = _adopt_elfie(client, csrf_token)
    body = DeviceRegistry(client.app.state.db_path).enroll(
        elfie_id, "模拟身体", "simulated"
    )
    begin_hosting(client.app.state.db_path, elfie_id, body.body_id, lease_seconds=30)

    profile = client.get(f"/api/v1/elfies/{elfie_id}/profile")

    assert profile.json()["embodiment"] == {"state": "switching_to_hosted"}


def test_owner_can_enroll_rotate_and_revoke_a_hashed_device_credential(
    client: TestClient,
) -> None:
    csrf_token = _login_owner(client)
    elfie_id = _adopt_elfie(client, csrf_token)
    enrolled = client.post(
        "/api/v1/owner/devices",
        json={"elfie_id": elfie_id, "display_name": "客厅玩具", "body_type": "toy"},
        headers={"X-CSRF-Token": csrf_token},
    )
    body_id = enrolled.json()["body_id"]
    original_bearer = enrolled.json()["bearer_token"]
    rotated = client.post(
        f"/api/v1/owner/devices/{body_id}/rotate?elfie_id={elfie_id}",
        headers={"X-CSRF-Token": csrf_token},
    )
    revoked = client.delete(
        f"/api/v1/owner/devices/{body_id}?elfie_id={elfie_id}",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert enrolled.status_code == 200
    assert original_bearer not in str(
        client.get(f"/api/v1/owner/devices?elfie_id={elfie_id}").json()
    )
    assert rotated.status_code == 200
    assert rotated.json()["bearer_token"] != original_bearer
    assert revoked.status_code == 200


def test_device_websocket_routes_typed_sensor_events_and_command_polls(
    client: TestClient,
) -> None:
    csrf_token = _login_owner(client)
    elfie_id = _adopt_elfie(client, csrf_token)
    enrolled = client.post(
        "/api/v1/owner/devices",
        json={"elfie_id": elfie_id, "display_name": "客厅玩具", "body_type": "toy"},
        headers={"X-CSRF-Token": csrf_token},
    )
    body_id = str(enrolled.json()["body_id"])
    bearer_token = str(enrolled.json()["bearer_token"])
    event = BodySensorEvent(
        event_id=EventId("device-sensor-1"),
        body_id=BodyId("living-room-toy"),
        source=ActorRef(actor_id=ActorId("device-owner"), source_kind="microphone"),
        occurred_at=datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc),
        received_at=datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc),
        payload=UtteranceFinal(kind="utterance_final", text="听见了吗？"),
    )
    received: list[BodySensorEvent] = []
    client.app.state.device_gateway.attach_sensor_handler(body_id, received.append)

    with client.websocket_connect(
        "/api/v1/ws/devices",
        headers={"Authorization": f"Bearer {bearer_token}"},
    ) as websocket:
        assert websocket.receive_json() == {"event": "ready", "body_id": body_id}
        websocket.send_json(
            {"event": "sensor_event", "sensor_event": event.model_dump(mode="json")}
        )
        assert websocket.receive_json() == {"event": "sensor_event", "delivered": True}

        command = SpeechCommand(
            command_type="speech",
            command_id=CommandId("device-command-1"),
            turn_id=TurnId("device-turn-1"),
            intent_id=IntentId("device-intent-1"),
            body_id=BodyId("living-room-toy"),
            issued_at=datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc),
            deadline=datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)
            + timedelta(seconds=10),
            capability_revision=1,
            text="你好，玩具。",
        )
        assert client.app.state.device_gateway.enqueue_command(body_id, command) is True
        websocket.send_json({"event": "command_poll"})
        command_batch = websocket.receive_json()

    assert received == [event]
    assert command_batch["event"] == "commands"
    assert command_batch["commands"] == [command.model_dump(mode="json")]


def test_v1_chat_websocket_requires_the_same_session_as_rest(
    client: TestClient,
) -> None:
    _login_owner(client)
    session_token = client.cookies.get("session_token")
    assert session_token

    with client.websocket_connect(
        "/api/v1/ws/chat", headers={"Cookie": f"session_token={session_token}"}
    ) as websocket:
        ready = websocket.receive_json()

    assert ready == {
        "event": "ready",
        "principal": {"role": "owner", "account_id": "owner"},
    }


def test_v1_session_projection_includes_the_owner_landing_preference(
    client: TestClient,
) -> None:
    _login_owner(client)

    response = client.get("/api/v1/me")

    assert response.status_code == 200
    assert response.json()["default_landing_page"] == "manage"


def test_v1_chat_websocket_persists_and_acknowledges_an_owned_message(
    client: TestClient,
) -> None:
    csrf_token = _login_owner(client)
    elfie_id = _adopt_elfie(client, csrf_token)
    session_token = client.cookies.get("session_token")
    assert session_token

    with client.websocket_connect(
        "/api/v1/ws/chat", headers={"Cookie": f"session_token={session_token}"}
    ) as websocket:
        assert websocket.receive_json()["event"] == "ready"
        websocket.send_json(
            {"event": "user_message", "elfie_id": elfie_id, "text": "你好，小白"}
        )
        acknowledgement = websocket.receive_json()

    assert acknowledgement["event"] == "message"
    assert acknowledgement["message"]["elfie_id"] == elfie_id
    assert acknowledgement["message"]["text"] == "你好，小白"


def test_v1_chat_websocket_receives_a_persisted_elfie_reply(client: TestClient) -> None:
    csrf_token = _login_owner(client)
    elfie_id = _adopt_elfie(client, csrf_token)
    user_id = int(client.get("/api/v1/me").json()["user_id"])
    session_token = client.cookies.get("session_token")
    assert session_token

    with client.websocket_connect(
        "/api/v1/ws/chat", headers={"Cookie": f"session_token={session_token}"}
    ) as websocket:
        assert websocket.receive_json()["event"] == "ready"
        record_elfie_chat_message(
            elfie_id,
            ElfieChatMessageInput(
                message_id="v1-reply-1",
                conversation_id=f"owner:{user_id}",
                user_id=user_id,
                sender=ElfieChatSender.ELFIE,
                text="我在这里。",
                channel="web",
            ),
        )
        client.app.state.v1_chat_hub.publish_elfie_reply(elfie_id)
        event = websocket.receive_json()

    assert event["event"] == "message"
    assert event["message"]["sender"] == "elfie"
    assert event["message"]["text"] == "我在这里。"


def test_legacy_runtime_reply_is_bridged_to_the_same_origin_chat_socket(
    client: TestClient,
) -> None:
    csrf_token = _login_owner(client)
    elfie_id = _adopt_elfie(client, csrf_token)
    session_token = client.cookies.get("session_token")
    assert session_token

    with client.websocket_connect(
        "/api/v1/ws/chat", headers={"Cookie": f"session_token={session_token}"}
    ) as websocket:
        assert websocket.receive_json()["event"] == "ready"
        client.app.state.ws_manager.broadcast_to_owners(
            elfie_id,
            {
                "action": "owner_message",
                "payload": {"parts": [{"type": "text", "text": "我听见你了。"}]},
            },
        )
        event = websocket.receive_json()

    assert event["event"] == "message"
    assert event["message"]["sender"] == "elfie"
    assert event["message"]["text"] == "我听见你了。"


def test_v1_openapi_route_snapshot(client: TestClient) -> None:
    paths = client.app.openapi()["paths"]

    assert {
        "/api/v1/me",
        "/api/v1/me/default-landing-page",
        "/api/v1/elfies",
        "/api/v1/elfies/{elfie_id}/profile",
        "/api/v1/conversations",
        "/api/v1/conversations/{elfie_id}/messages",
    } <= set(paths)
