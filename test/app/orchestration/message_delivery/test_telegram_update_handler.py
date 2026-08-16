from __future__ import annotations

from unittest.mock import MagicMock

from app.features.accounts import AccountPrincipal
from app.features.communication import CommunicationFacade, MessageResult
from app.features.communication.telegram_models import (
    AuthorizedTelegramMessage,
    TelegramPairingCompletion,
)
from app.features.communication.telegram_port_models import (
    StoredTelegramAccount,
    TelegramPrivateUpdate,
)
from app.features.communication.telegram_service import TelegramAccountsService
from app.orchestration.message_delivery import (
    DuplicateMessage,
    MessageDeliveryFacade,
    MessageDeliveryUnavailable,
    SubmittedMessageResult,
    TelegramUpdateHandler,
)


def _account() -> StoredTelegramAccount:
    return StoredTelegramAccount(
        elfie_id="00000001",
        bot_id="991",
        bot_username="elfienest_star_bot",
        display_name="星星",
        credential_ref="ELFIE_TELEGRAM_00000001_BOT_TOKEN",
        configured_owner_user_id=7,
        status="active",
        last_checked_at="t0",
        issue=None,
    )


def _update(text: str | None = "你好") -> TelegramPrivateUpdate:
    return TelegramPrivateUpdate(
        update_id=42,
        message_id=9,
        chat_id="1701",
        chat_type="private",
        telegram_user_id="701",
        telegram_username="owner_seven",
        display_name="七号主人",
        text=text,
    )


def _authorized() -> AuthorizedTelegramMessage:
    return AuthorizedTelegramMessage(
        elfie_id="00000001",
        principal=AccountPrincipal(7, "owner-seven", "user", "chat"),
        conversation_id="telegram:1701",
        external_actor_id="701",
        external_actor_display_name="七号主人",
    )


def _message() -> MessageResult:
    return MessageResult(1, "00000001", "user", "你好", "t0")


def test_pairing_command_never_enters_brain_and_returns_confirmation() -> None:
    accounts = MagicMock(spec=TelegramAccountsService)
    accounts.complete_pairing.return_value = TelegramPairingCompletion(True)
    delivery = MagicMock(spec=MessageDeliveryFacade)
    handler = TelegramUpdateHandler(
        accounts, delivery, MagicMock(spec=CommunicationFacade)
    )

    outcome = handler.handle(_account(), _update("/start code"), pairing_code="code")

    assert outcome.terminal is True
    assert outcome.reply_text == "配对成功，现在可以和精灵聊天了。"
    delivery.submit_user_message.assert_not_called()


def test_only_bound_private_text_reaches_canonical_delivery_with_platform_identity() -> (
    None
):
    accounts = MagicMock(spec=TelegramAccountsService)
    accounts.authorize_inbound.return_value = _authorized()
    delivery = MagicMock(spec=MessageDeliveryFacade)
    delivery.submit_user_message.return_value = SubmittedMessageResult(_message())
    handler = TelegramUpdateHandler(
        accounts, delivery, MagicMock(spec=CommunicationFacade)
    )

    outcome = handler.handle(_account(), _update())

    assert outcome.terminal is True
    command = delivery.submit_user_message.call_args.args[1]
    assert command.channel == "telegram"
    assert command.conversation_id == "telegram:1701"
    assert command.external_actor_id == "701"
    assert command.external_message_id == "telegram:991:update:42"


def test_unknown_sender_is_terminally_ignored_without_reply_or_brain_access() -> None:
    accounts = MagicMock(spec=TelegramAccountsService)
    accounts.authorize_inbound.return_value = None
    delivery = MagicMock(spec=MessageDeliveryFacade)
    handler = TelegramUpdateHandler(
        accounts, delivery, MagicMock(spec=CommunicationFacade)
    )

    outcome = handler.handle(_account(), _update())

    assert outcome.terminal is True
    assert outcome.reply_text is None
    delivery.submit_user_message.assert_not_called()


def test_runtime_unavailable_retries_same_update_without_advancing_cursor() -> None:
    accounts = MagicMock(spec=TelegramAccountsService)
    accounts.authorize_inbound.return_value = _authorized()
    delivery = MagicMock(spec=MessageDeliveryFacade)
    delivery.submit_user_message.side_effect = MessageDeliveryUnavailable("offline")
    handler = TelegramUpdateHandler(
        accounts, delivery, MagicMock(spec=CommunicationFacade)
    )

    outcome = handler.handle(_account(), _update())

    assert outcome.terminal is False
    assert outcome.reply_text is None


def test_replayed_brain_admission_repairs_idempotent_history_before_ack() -> None:
    accounts = MagicMock(spec=TelegramAccountsService)
    accounts.authorize_inbound.return_value = _authorized()
    delivery = MagicMock(spec=MessageDeliveryFacade)
    delivery.submit_user_message.side_effect = DuplicateMessage("duplicate")
    communication = MagicMock(spec=CommunicationFacade)
    communication.record_user_message.return_value = _message()
    handler = TelegramUpdateHandler(accounts, delivery, communication)

    outcome = handler.handle(_account(), _update())

    assert outcome.terminal is True
    repaired = communication.record_user_message.call_args.args[1]
    assert repaired.message_id == "telegram:991:update:42"
    assert repaired.conversation_id == "telegram:1701"
