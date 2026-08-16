"""Product rules for owner-managed Telegram accounts and pairing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from app.features.accounts import AccountPrincipal
from app.features.communication.telegram_errors import (
    TelegramAccountConflict,
    TelegramAccountInvalid,
    TelegramAccountNotFound,
)
from app.features.communication.telegram_models import (
    ConfigureTelegramAccountCommand,
    CreateTelegramPairingSessionCommand,
    GetTelegramAccountQuery,
)
from app.features.communication.telegram_port_models import (
    StoredTelegramAccount,
    StoredTelegramBinding,
    TelegramBotInspection,
    TelegramPrivateUpdate,
)
from app.features.communication.telegram_service import TelegramAccountsService

NOW = datetime(2026, 8, 16, 1, 0, tzinfo=timezone.utc)


def _principal(
    user_id: int = 7, account_id: str = "owner-seven", role: str = "user"
) -> AccountPrincipal:
    return AccountPrincipal(user_id, account_id, role, "chat")  # type: ignore[arg-type]


class Store:
    def __init__(self) -> None:
        self.owner_id = 7
        self.account: StoredTelegramAccount | None = None
        self.binding: StoredTelegramBinding | None = None
        self.cursor: int | None = None
        self.saved: list[StoredTelegramAccount] = []
        self.disconnected = False

    def owner_user_id(self, elfie_id: str):
        return self.owner_id if elfie_id == "00000001" else None

    def get_account(self, elfie_id: str):
        return self.account if elfie_id == "00000001" else None

    def list_active_accounts(self):
        return () if self.account is None else (self.account,)

    def save_account(self, account: StoredTelegramAccount) -> None:
        self.account = account
        self.saved.append(account)

    def mark_account_health(self, elfie_id: str, *, status, checked_at, issue):
        assert self.account is not None
        self.account = StoredTelegramAccount(
            **{
                **self.account.__dict__,
                "status": status,
                "last_checked_at": checked_at,
                "issue": issue,
            }
        )

    def disconnect_account(self, elfie_id: str, *, disconnected_at: str) -> None:
        self.disconnected = True
        self.account = None
        self.binding = None
        self.cursor = None

    def replace_binding(self, binding: StoredTelegramBinding) -> None:
        self.binding = binding

    def get_binding(self, elfie_id: str):
        return self.binding if elfie_id == "00000001" else None

    def next_update_id(self, elfie_id: str):
        return self.cursor

    def save_next_update_id(self, elfie_id: str, *, next_update_id, synced_at):
        self.cursor = next_update_id


class Tokens:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def credential_ref(self, elfie_id: str) -> str:
        return f"ELFIE_TELEGRAM_{elfie_id}_BOT_TOKEN"

    def load(self, credential_ref: str) -> str:
        return self.values.get(credential_ref, "")

    def replace(self, elfie_id: str, token: str) -> str:
        reference = self.credential_ref(elfie_id)
        self.values[reference] = token
        return reference

    def delete(self, elfie_id: str) -> None:
        self.values.pop(self.credential_ref(elfie_id), None)


class Inspector:
    def __init__(self, webhook_url: str = "") -> None:
        self.webhook_url = webhook_url
        self.tokens: list[str] = []

    def inspect_bot(self, bot_token: str) -> TelegramBotInspection:
        self.tokens.append(bot_token)
        return TelegramBotInspection(
            bot_id="991",
            username="elfienest_star_bot",
            display_name="星星的机器人",
            webhook_url=self.webhook_url,
        )


class Principals:
    def __init__(self) -> None:
        self.current = _principal()

    def find_principal(self, user_id: int):
        return self.current if self.current.user_id == user_id else None


def _service(
    store: Store | None = None,
    tokens: Tokens | None = None,
    inspector: Inspector | None = None,
) -> tuple[TelegramAccountsService, Store, Tokens, Inspector, Principals]:
    selected_store = store or Store()
    selected_tokens = tokens or Tokens()
    selected_inspector = inspector or Inspector()
    principals = Principals()
    service = TelegramAccountsService(
        selected_store,
        selected_tokens,
        selected_inspector,
        principals,
        now=lambda: NOW,
        pairing_token=lambda: "p" * 43,
    )
    return service, selected_store, selected_tokens, selected_inspector, principals


def _configured(store: Store, tokens: Tokens) -> None:
    reference = tokens.replace("00000001", "991:secret-token-value")
    store.account = StoredTelegramAccount(
        elfie_id="00000001",
        bot_id="991",
        bot_username="elfienest_star_bot",
        display_name="星星的机器人",
        credential_ref=reference,
        configured_owner_user_id=7,
        status="active",
        last_checked_at="2026-08-16T01:00:00.000Z",
        issue=None,
    )


def _update(text: str | None, *, user_id: str = "701") -> TelegramPrivateUpdate:
    return TelegramPrivateUpdate(
        update_id=42,
        message_id=9,
        chat_id="1701",
        chat_type="private",
        telegram_user_id=user_id,
        telegram_username="owner_seven",
        display_name="七号主人",
        text=text,
    )


def test_global_admin_cannot_read_or_configure_an_elfie_they_do_not_own() -> None:
    service, store, tokens, inspector, _ = _service()
    global_admin = _principal(8, "global-admin", "admin")

    with pytest.raises(TelegramAccountNotFound):
        service.get_account(global_admin, GetTelegramAccountQuery("00000001"))
    with pytest.raises(TelegramAccountNotFound):
        service.configure_account(
            global_admin,
            ConfigureTelegramAccountCommand("00000001", "991:secret-token-value"),
        )

    assert inspector.tokens == []
    assert tokens.values == {}
    assert store.saved == []


def test_valid_token_is_verified_then_saved_without_ever_returning_plaintext() -> None:
    service, store, tokens, inspector, _ = _service()

    result = service.configure_account(
        _principal(),
        ConfigureTelegramAccountCommand("00000001", "991:secret-token-value"),
    )

    assert inspector.tokens == ["991:secret-token-value"]
    assert tokens.values == {
        "ELFIE_TELEGRAM_00000001_BOT_TOKEN": "991:secret-token-value"
    }
    assert store.saved[0].bot_id == "991"
    assert result.state == "waiting_pairing"
    assert result.bot_username == "elfienest_star_bot"
    assert "secret" not in repr(result).lower()


def test_existing_webhook_is_rejected_without_touching_secret_or_store() -> None:
    service, store, tokens, _, _ = _service(
        inspector=Inspector("https://example.invalid/hook")
    )

    with pytest.raises(TelegramAccountConflict, match="Webhook"):
        service.configure_account(
            _principal(),
            ConfigureTelegramAccountCommand("00000001", "991:secret-token-value"),
        )

    assert tokens.values == {}
    assert store.saved == []


def test_one_time_pairing_binds_only_private_human_start_and_cannot_replay() -> None:
    service, store, tokens, _, _ = _service()
    _configured(store, tokens)
    pairing = service.create_pairing_session(
        _principal(), CreateTelegramPairingSessionCommand("00000001")
    )
    parsed = urlparse(pairing.deep_link)
    code = parse_qs(parsed.query)["start"][0]

    rejected = service.complete_pairing(
        store.account,  # type: ignore[arg-type]
        _update(f"/start {code}", user_id="702"),
        code,
    )
    assert rejected.completed is True
    assert store.binding is not None
    assert store.binding.telegram_user_id == "702"

    replay = service.complete_pairing(
        store.account,  # type: ignore[arg-type]
        _update(f"/start {code}"),
        code,
    )
    assert replay.completed is False
    assert replay.reason == "pairing_expired"


def test_bound_identity_is_the_only_external_sender_authorized_for_brain() -> None:
    service, store, tokens, _, principals = _service()
    _configured(store, tokens)
    store.binding = StoredTelegramBinding(
        elfie_id="00000001",
        telegram_user_id="701",
        telegram_chat_id="1701",
        telegram_username="owner_seven",
        display_name="七号主人",
        local_owner_user_id=7,
        local_owner_account_id="owner-seven",
        conversation_id="telegram:1701",
        bound_at="2026-08-16T01:05:00.000Z",
    )

    authorized = service.authorize_inbound(store.account, _update("你好"))  # type: ignore[arg-type]
    stranger = service.authorize_inbound(
        store.account,
        _update("你好", user_id="999"),  # type: ignore[arg-type]
    )

    assert authorized is not None
    assert authorized.principal == principals.current
    assert authorized.conversation_id == "telegram:1701"
    assert stranger is None


def test_owner_change_stops_runtime_account_until_new_owner_reconfigures() -> None:
    service, store, tokens, _, _ = _service()
    _configured(store, tokens)
    store.owner_id = 8

    assert service.runtime_accounts() == ()
    assert store.account is not None
    assert store.account.status == "attention"
    assert store.account.issue == "owner_changed"


def test_attention_account_cannot_start_pairing_or_runtime() -> None:
    service, store, tokens, _, _ = _service()
    _configured(store, tokens)
    assert store.account is not None
    store.account = StoredTelegramAccount(
        **{
            **store.account.__dict__,
            "status": "attention",
            "issue": "telegram_unavailable",
        }
    )

    with pytest.raises(TelegramAccountInvalid, match="重新配置"):
        service.create_pairing_session(
            _principal(), CreateTelegramPairingSessionCommand("00000001")
        )
    assert service.runtime_accounts() == ()


def test_pairing_session_expires_after_ten_minutes() -> None:
    current = NOW
    store = Store()
    tokens = Tokens()
    _configured(store, tokens)
    service = TelegramAccountsService(
        store,
        tokens,
        Inspector(),
        Principals(),
        now=lambda: current,
        pairing_token=lambda: "q" * 43,
    )
    pairing = service.create_pairing_session(
        _principal(), CreateTelegramPairingSessionCommand("00000001")
    )
    code = parse_qs(urlparse(pairing.deep_link).query)["start"][0]
    current = NOW + timedelta(minutes=10, seconds=1)

    result = service.complete_pairing(
        store.account,
        _update(f"/start {code}"),
        code,  # type: ignore[arg-type]
    )

    assert result.completed is False
    assert result.reason == "pairing_expired"
