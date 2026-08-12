from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.features.accounts import AccountPrincipal
from app.features.communication import (
    CommunicationFacade,
    ConversationMessageWrite,
    StoredConversationMessage,
)
from app.features.elfies import ElfiesService
from app.interfaces.api.v1.auth import require_user
from app.interfaces.api.v1.me.conversations import router as conversations_router
from app.interfaces.api.v1.realtime.chat import router as realtime_router
from app.orchestration.message_delivery import (
    DeliverElfieReplyCommand,
    DeliveryAdmission,
    MessageDeliveryFacade,
    UserMessageDeliveryAttempt,
)
from infrastructure.communication import SameOriginMessagePublisher


class MemoryHistory:
    def __init__(self) -> None:
        self.messages: list[StoredConversationMessage] = []

    def list_messages(
        self,
        elfie_id: str,
        *,
        conversation_id: str,
        user_id: int,
    ) -> tuple[StoredConversationMessage, ...]:
        return tuple(self.messages)

    def append_message(
        self, message: ConversationMessageWrite
    ) -> StoredConversationMessage:
        stored = StoredConversationMessage(
            id=len(self.messages) + 1,
            sender=message.sender,
            text=message.text,
            created_at=f"2026-08-11T00:00:0{len(self.messages)}.000Z",
        )
        self.messages.append(stored)
        return stored

    def owner_user_id(self, elfie_id: str) -> int | None:
        return 7 if elfie_id == "00000001" else None


class AcceptedDelivery:
    def deliver_user_message(
        self, attempt: UserMessageDeliveryAttempt
    ) -> DeliveryAdmission:
        return DeliveryAdmission(status="accepted")


def _application() -> tuple[FastAPI, MemoryHistory]:
    principal = AccountPrincipal(7, "owner", "owner", "chat")
    profile = SimpleNamespace(elfie_id="00000001", name="小白")
    elfies = MagicMock(spec=ElfiesService)
    elfies.list_visible.return_value = (SimpleNamespace(profile=profile),)
    elfies.get_profile.return_value = SimpleNamespace(profile=profile)
    history = MemoryHistory()
    communication = CommunicationFacade(history, elfies)
    accounts = SimpleNamespace(active=True)
    accounts.authenticate_session = lambda _token: (
        principal if accounts.active else None
    )
    realtime = SameOriginMessagePublisher(
        lambda token, user_id: (
            (current := accounts.authenticate_session(token)) is not None
            and current.user_id == user_id
        )
    )
    delivery = MessageDeliveryFacade(communication, AcceptedDelivery(), realtime)
    application = FastAPI()
    application.include_router(conversations_router)
    application.include_router(realtime_router)
    application.dependency_overrides[require_user] = lambda: principal
    application.state.communication = communication
    application.state.message_delivery = delivery
    application.state.communication_realtime = realtime
    application.state.accounts = accounts
    application.state.service_access_policy = SimpleNamespace(
        mode=SimpleNamespace(value="loopback"),
        allows_origin=lambda _origin: True,
    )
    return application, history


def test_http_resources_use_strict_me_conversation_envelopes() -> None:
    application, _history = _application()
    with TestClient(application) as client:
        listing = client.get("/api/v1/me/conversations")
        sent = client.post(
            "/api/v1/me/conversations/00000001/messages",
            json={"text": "你好"},
        )
        messages = client.get("/api/v1/me/conversations/00000001/messages")

    assert listing.status_code == 200
    assert set(listing.json()) == {"items"}
    assert sent.status_code == 201
    assert sent.json()["text"] == "你好"
    assert messages.json()["items"] == [sent.json()]


def test_websocket_ack_and_persisted_reply_keep_the_existing_event_shapes() -> None:
    application, history = _application()
    with TestClient(application) as client:
        with client.websocket_connect(
            "/api/v1/ws/chat",
            headers={"Cookie": "session_token=test-session"},
        ) as websocket:
            assert websocket.receive_json() == {
                "event": "ready",
                "principal": {"role": "owner", "account_id": "owner"},
            }
            websocket.send_json(
                {"event": "user_message", "elfie_id": "00000001", "text": "你好"}
            )
            assert websocket.receive_json()["message"]["sender"] == "user"
            application.state.message_delivery.deliver_elfie_reply(
                DeliverElfieReplyCommand(elfie_id="00000001", text="我很好")
            )
            reply = websocket.receive_json()

    assert reply["event"] == "message"
    assert reply["message"]["sender"] == "elfie"
    assert [item.text for item in history.messages] == ["你好", "我很好"]


def test_revoked_session_is_closed_before_an_elfie_reply_is_published() -> None:
    application, _history = _application()
    with TestClient(application) as client:
        with client.websocket_connect(
            "/api/v1/ws/chat",
            headers={"Cookie": "session_token=test-session"},
        ) as websocket:
            assert websocket.receive_json()["event"] == "ready"
            application.state.accounts.active = False
            application.state.message_delivery.deliver_elfie_reply(
                DeliverElfieReplyCommand(elfie_id="00000001", text="不会发送")
            )
            with pytest.raises(WebSocketDisconnect) as closed:
                websocket.receive_json()

    assert closed.value.code == 4004
