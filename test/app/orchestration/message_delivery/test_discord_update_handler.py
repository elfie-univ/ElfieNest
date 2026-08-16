from __future__ import annotations

from unittest.mock import MagicMock

from app.features.accounts import AccountPrincipal
from app.features.communication import CommunicationFacade
from app.features.communication.discord_models import (
    AuthorizedDiscordMessage,
    DiscordPairingCompletion,
)
from app.features.communication.discord_port_models import (
    DiscordPrivateUpdate,
    StoredDiscordAccount,
)
from app.features.communication.discord_service import DiscordAccountsService
from app.orchestration.message_delivery import (
    DiscordUpdateHandler,
    MessageDeliveryFacade,
    MessageDeliveryUnavailable,
    SubmittedMessageResult,
)


def _account() -> StoredDiscordAccount:
    return StoredDiscordAccount(
        "00000001",
        "991",
        "elfienest_star",
        "星星",
        "ELFIE_DISCORD_00000001_BOT_TOKEN",
        7,
        "active",
        "t0",
        None,
    )


def _update(text: str | None = "你好") -> DiscordPrivateUpdate:
    return DiscordPrivateUpdate(
        "message-42", "1701", "701", "owner_seven", "七号主人", text, True
    )


def _authorized() -> AuthorizedDiscordMessage:
    return AuthorizedDiscordMessage(
        "00000001",
        AccountPrincipal(7, "owner-seven", "user", "chat"),
        "discord:1701",
        "701",
        "七号主人",
    )


def test_pairing_confirmation_never_enters_canonical_delivery() -> None:
    accounts = MagicMock(spec=DiscordAccountsService)
    accounts.complete_pairing.return_value = DiscordPairingCompletion(True)
    delivery = MagicMock(spec=MessageDeliveryFacade)
    handler = DiscordUpdateHandler(
        accounts, delivery, MagicMock(spec=CommunicationFacade)
    )

    outcome = handler.handle(
        _account(), _update("pairing-code"), pairing_code="pairing-code"
    )

    assert outcome.terminal is True
    assert outcome.reply_text == "配对成功，现在可以和精灵聊天了。"
    delivery.submit_user_message.assert_not_called()


def test_only_authorized_dm_reaches_canonical_delivery_with_discord_identity() -> None:
    accounts = MagicMock(spec=DiscordAccountsService)
    accounts.authorize_inbound.return_value = _authorized()
    delivery = MagicMock(spec=MessageDeliveryFacade)
    delivery.submit_user_message.return_value = SubmittedMessageResult(MagicMock())
    handler = DiscordUpdateHandler(
        accounts, delivery, MagicMock(spec=CommunicationFacade)
    )

    outcome = handler.handle(_account(), _update())
    command = delivery.submit_user_message.call_args.args[1]

    assert outcome.terminal is True
    assert command.channel == "discord"
    assert command.conversation_id == "discord:1701"
    assert command.external_actor_id == "701"
    assert command.external_message_id == "discord:991:message:message-42"


def test_unknown_sender_is_terminally_ignored_without_token_or_brain_work() -> None:
    accounts = MagicMock(spec=DiscordAccountsService)
    accounts.authorize_inbound.return_value = None
    delivery = MagicMock(spec=MessageDeliveryFacade)
    handler = DiscordUpdateHandler(
        accounts, delivery, MagicMock(spec=CommunicationFacade)
    )

    outcome = handler.handle(_account(), _update())

    assert outcome.terminal is True
    assert outcome.reply_text is None
    delivery.submit_user_message.assert_not_called()


def test_delivery_failure_keeps_gateway_event_retryable() -> None:
    accounts = MagicMock(spec=DiscordAccountsService)
    accounts.authorize_inbound.return_value = _authorized()
    delivery = MagicMock(spec=MessageDeliveryFacade)
    delivery.submit_user_message.side_effect = MessageDeliveryUnavailable("offline")
    handler = DiscordUpdateHandler(
        accounts, delivery, MagicMock(spec=CommunicationFacade)
    )

    assert handler.handle(_account(), _update()).terminal is False
