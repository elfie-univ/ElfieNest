from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.accounts import AccountPrincipal
from app.features.communication.discord_models import (
    DiscordAccountResult,
    DiscordPairingSessionResult,
)
from app.features.communication.discord_service import DiscordAccountsService
from app.interfaces.api.v1.auth import require_user
from app.interfaces.api.v1.elfies.communication_accounts import router


def _principal() -> AccountPrincipal:
    return AccountPrincipal(7, "member", "user", "chat")


class StubService(DiscordAccountsService):
    def __init__(self) -> None:
        self.configured: tuple[str, str] | None = None
        self.paired: str | None = None
        self.disconnected: str | None = None

    def get_account(self, principal, query):
        return _result(query.elfie_id)

    def configure_account(self, principal, command):
        self.configured = (command.elfie_id, command.bot_token)
        return _result(command.elfie_id, "waiting_pairing")

    def create_pairing_session(self, principal, command):
        self.paired = command.elfie_id
        return DiscordPairingSessionResult(
            "https://discord.com/oauth2/authorize?client_id=1",
            "https://discord.com/users/1",
            "opaque-code",
            "2026-08-16T01:10:00.000Z",
        )

    def disconnect_account(self, principal, command):
        self.disconnected = command.elfie_id
        return _result(command.elfie_id, "unconfigured")


def _result(elfie_id: str, state: str = "active") -> DiscordAccountResult:
    configured = state != "unconfigured"
    return DiscordAccountResult(
        elfie_id=elfie_id,
        state=state,  # type: ignore[arg-type]
        bot_username="elfienest_star" if configured else None,
        bot_display_name="星星" if configured else None,
        bound_discord_username="owner_seven" if state == "active" else None,
        bound_display_name="七号主人" if state == "active" else None,
        last_checked_at="2026-08-16T01:00:00.000Z" if configured else None,
        issue=None,
    )


def _client() -> tuple[TestClient, StubService]:
    app = FastAPI()
    service = StubService()
    app.state.discord_accounts = service
    app.include_router(router)
    app.dependency_overrides[require_user] = _principal
    return TestClient(app), service


def test_discord_resource_never_returns_token_or_accepts_client_owner() -> None:
    client, service = _client()
    root = "/api/v1/elfies/00000001/communication-accounts/discord"

    read = client.get(root)
    saved = client.put(root, json={"bot_token": "discord-secret-token"})
    rejected = client.put(
        root, json={"bot_token": "discord-secret-token", "owner_user_id": 99}
    )

    assert read.status_code == 200
    assert "token" not in read.text.lower()
    assert saved.status_code == 200
    assert "discord-secret-token" not in saved.text
    assert service.configured == ("00000001", "discord-secret-token")
    assert rejected.status_code == 422


def test_pairing_install_and_disconnect_stay_under_owner_elfie_resource() -> None:
    client, service = _client()
    root = "/api/v1/elfies/00000001/communication-accounts/discord"

    pairing = client.post(f"{root}/pairing-sessions")
    disconnected = client.delete(root)

    assert pairing.status_code == 201
    assert pairing.json()["invite_url"].startswith("https://discord.com/oauth2/")
    assert pairing.json()["pairing_code"] == "opaque-code"
    assert disconnected.status_code == 200
    assert disconnected.json()["state"] == "unconfigured"
    assert service.paired == "00000001"
    assert service.disconnected == "00000001"
