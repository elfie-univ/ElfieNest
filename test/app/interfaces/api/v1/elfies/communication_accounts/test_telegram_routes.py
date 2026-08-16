from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.accounts import AccountPrincipal
from app.features.communication.telegram_models import (
    TelegramAccountResult,
    TelegramPairingSessionResult,
)
from app.features.communication.telegram_service import TelegramAccountsService
from app.interfaces.api.v1.auth import require_user
from app.interfaces.api.v1.elfies.communication_accounts import router


def _principal() -> AccountPrincipal:
    return AccountPrincipal(7, "member", "user", "chat")


class StubService(TelegramAccountsService):
    def __init__(self) -> None:
        self.configured: tuple[str, str] | None = None
        self.disconnected: str | None = None
        self.paired: str | None = None

    def get_account(self, principal, query):
        return _result(query.elfie_id)

    def configure_account(self, principal, command):
        self.configured = (command.elfie_id, command.bot_token)
        return _result(command.elfie_id, "waiting_pairing")

    def disconnect_account(self, principal, command):
        self.disconnected = command.elfie_id
        return _result(command.elfie_id, "unconfigured")

    def create_pairing_session(self, principal, command):
        self.paired = command.elfie_id
        return TelegramPairingSessionResult(
            "https://t.me/elfienest_star_bot?start=opaque", "2026-08-16T01:10:00.000Z"
        )


def _result(elfie_id: str, state: str = "active") -> TelegramAccountResult:
    configured = state != "unconfigured"
    return TelegramAccountResult(
        elfie_id=elfie_id,
        state=state,  # type: ignore[arg-type]
        bot_username="elfienest_star_bot" if configured else None,
        bot_display_name="星星" if configured else None,
        bound_telegram_username="owner_seven" if state == "active" else None,
        bound_display_name="七号主人" if state == "active" else None,
        last_checked_at="2026-08-16T01:00:00.000Z" if configured else None,
        issue=None,
    )


def _client() -> tuple[TestClient, StubService]:
    app = FastAPI()
    service = StubService()
    app.state.telegram_accounts = service
    app.include_router(router)
    app.dependency_overrides[require_user] = _principal
    return TestClient(app), service


def test_resource_never_returns_token_and_rejects_client_supplied_owner() -> None:
    client, service = _client()

    read = client.get("/api/v1/elfies/00000001/communication-accounts/telegram")
    saved = client.put(
        "/api/v1/elfies/00000001/communication-accounts/telegram",
        json={"bot_token": "991:secret-token-value"},
    )
    rejected = client.put(
        "/api/v1/elfies/00000001/communication-accounts/telegram",
        json={"bot_token": "991:secret-token-value", "owner_user_id": 99},
    )

    assert read.status_code == 200
    assert "token" not in read.text.lower()
    assert saved.status_code == 200
    assert "secret-token-value" not in saved.text
    assert service.configured == ("00000001", "991:secret-token-value")
    assert rejected.status_code == 422


def test_pairing_and_disconnect_are_nested_under_owner_elfie_resource() -> None:
    client, service = _client()
    root = "/api/v1/elfies/00000001/communication-accounts/telegram"

    pairing = client.post(f"{root}/pairing-sessions")
    disconnected = client.delete(root)

    assert pairing.status_code == 201
    assert pairing.json()["deep_link"].startswith("https://t.me/")
    assert disconnected.status_code == 200
    assert disconnected.json()["state"] == "unconfigured"
    assert service.paired == "00000001"
    assert service.disconnected == "00000001"
