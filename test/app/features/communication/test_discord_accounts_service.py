"""Product rules for owner-managed Discord accounts and pairing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.features.accounts import AccountPrincipal
from app.features.communication.discord_errors import (
    DiscordAccountInvalid,
    DiscordAccountNotFound,
)
from app.features.communication.discord_models import (
    ConfigureDiscordAccountCommand,
    CreateDiscordPairingSessionCommand,
)
from app.features.communication.discord_port_models import (
    DiscordBotInspection,
    DiscordPrivateUpdate,
    StoredDiscordAccount,
    StoredDiscordBinding,
)
from app.features.communication.discord_service import DiscordAccountsService

NOW = datetime(2026, 8, 16, 1, 0, tzinfo=timezone.utc)


def _principal(user_id: int = 7, account_id: str = "owner-seven") -> AccountPrincipal:
    return AccountPrincipal(user_id, account_id, "user", "chat")  # type: ignore[arg-type]


class Store:
    def __init__(self) -> None:
        self.owner_id = 7
        self.account: StoredDiscordAccount | None = None
        self.binding: StoredDiscordBinding | None = None
        self.saved: list[StoredDiscordAccount] = []

    def owner_user_id(self, elfie_id: str):
        return self.owner_id if elfie_id == "00000001" else None

    def get_account(self, elfie_id: str):
        return self.account if elfie_id == "00000001" else None

    def list_active_accounts(self):
        return () if self.account is None else (self.account,)

    def save_account(self, account: StoredDiscordAccount) -> None:
        self.account = account
        self.saved.append(account)

    def mark_account_health(self, elfie_id: str, *, status, checked_at, issue):
        assert self.account is not None
        self.account = StoredDiscordAccount(
            **{
                **self.account.__dict__,
                "status": status,
                "last_checked_at": checked_at,
                "issue": issue,
            }
        )

    def disconnect_account(self, elfie_id: str, *, disconnected_at: str) -> None:
        self.account = None
        self.binding = None

    def replace_binding(self, binding: StoredDiscordBinding) -> None:
        self.binding = binding

    def get_binding(self, elfie_id: str):
        return self.binding if elfie_id == "00000001" else None


class Tokens:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def credential_ref(self, elfie_id: str) -> str:
        return f"ELFIE_DISCORD_{elfie_id}_BOT_TOKEN"

    def load(self, credential_ref: str) -> str:
        return self.values.get(credential_ref, "")

    def replace(self, elfie_id: str, token: str) -> str:
        reference = self.credential_ref(elfie_id)
        self.values[reference] = token
        return reference

    def delete(self, elfie_id: str) -> None:
        self.values.pop(self.credential_ref(elfie_id), None)


class Inspector:
    def inspect_bot(self, bot_token: str) -> DiscordBotInspection:
        return DiscordBotInspection("991", "elfienest_star", "星星机器人")


class Principals:
    def find_principal(self, user_id: int):
        return _principal() if user_id == 7 else None


def _service(now=lambda: NOW):
    store = Store()
    tokens = Tokens()
    service = DiscordAccountsService(
        store,
        tokens,
        Inspector(),
        Principals(),
        now=now,
        pairing_token=lambda: "pairing-code",
    )
    return service, store, tokens


def _configure(store: Store, tokens: Tokens) -> None:
    reference = tokens.replace("00000001", "discord-secret-token")
    store.account = StoredDiscordAccount(
        "00000001",
        "991",
        "elfienest_star",
        "星星机器人",
        reference,
        7,
        "active",
        "t0",
        None,
    )


def _update(
    text: str | None, *, user_id: str = "701", channel_id: str = "1701"
) -> DiscordPrivateUpdate:
    return DiscordPrivateUpdate(
        message_id="message-42",
        channel_id=channel_id,
        discord_user_id=user_id,
        discord_username="owner_seven",
        display_name="七号主人",
        text=text,
        is_dm=True,
    )


def test_owner_boundary_rejects_other_users_before_token_inspection() -> None:
    service, store, tokens = _service()
    with pytest.raises(DiscordAccountNotFound):
        service.configure_account(
            _principal(8, "global-admin"),
            ConfigureDiscordAccountCommand("00000001", "discord-secret-token"),
        )
    assert store.saved == []
    assert tokens.values == {}


def test_valid_token_is_inspected_then_saved_without_returning_plaintext() -> None:
    service, store, tokens = _service()
    result = service.configure_account(
        _principal(), ConfigureDiscordAccountCommand("00000001", "discord-secret-token")
    )
    assert result.state == "waiting_pairing"
    assert store.saved[0].bot_id == "991"
    assert "discord-secret-token" not in repr(result)
    assert tokens.values["ELFIE_DISCORD_00000001_BOT_TOKEN"] == "discord-secret-token"


def test_pairing_binds_one_private_human_and_replay_fails() -> None:
    service, store, tokens = _service()
    _configure(store, tokens)
    pairing = service.create_pairing_session(
        _principal(), CreateDiscordPairingSessionCommand("00000001")
    )
    assert pairing.pairing_code == "pairing-code"
    assert "scope=bot%20applications.commands" in pairing.invite_url

    completed = service.complete_pairing(
        store.account, _update(pairing.pairing_code), pairing.pairing_code
    )  # type: ignore[arg-type]
    replay = service.complete_pairing(
        store.account,
        _update(pairing.pairing_code, user_id="702"),
        pairing.pairing_code,
    )  # type: ignore[arg-type]
    assert completed.completed is True
    assert replay.completed is False
    assert store.binding is not None
    assert store.binding.conversation_id == "discord:1701"


def test_only_exact_bound_dm_is_authorized_and_public_messages_are_ignored() -> None:
    service, store, tokens = _service()
    _configure(store, tokens)
    store.binding = StoredDiscordBinding(
        "00000001",
        "701",
        "1701",
        "owner_seven",
        "七号主人",
        7,
        "owner-seven",
        "discord:1701",
        "t0",
    )
    assert service.authorize_inbound(store.account, _update("你好")) is not None  # type: ignore[arg-type]
    assert (
        service.authorize_inbound(store.account, _update("你好", user_id="999")) is None
    )  # type: ignore[arg-type]
    assert (
        service.authorize_inbound(
            store.account,
            DiscordPrivateUpdate(
                "m", "1701", "701", "owner_seven", "七号主人", "你好", False
            ),
        )
        is None
    )  # type: ignore[arg-type]


def test_pairing_expires_after_ten_minutes() -> None:
    current = NOW
    service, store, tokens = _service(now=lambda: current)
    _configure(store, tokens)
    pairing = service.create_pairing_session(
        _principal(), CreateDiscordPairingSessionCommand("00000001")
    )
    current = NOW + timedelta(minutes=10, seconds=1)
    result = service.complete_pairing(
        store.account, _update(pairing.pairing_code), pairing.pairing_code
    )  # type: ignore[arg-type]
    assert result.completed is False
    assert result.reason == "pairing_expired"


def test_attention_account_cannot_start_pairing() -> None:
    service, store, tokens = _service()
    _configure(store, tokens)
    assert store.account is not None
    store.account = StoredDiscordAccount(
        **{**store.account.__dict__, "status": "attention"}
    )
    with pytest.raises(DiscordAccountInvalid):
        service.create_pairing_session(
            _principal(), CreateDiscordPairingSessionCommand("00000001")
        )
