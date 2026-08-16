from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.features.accounts import AccountPrincipal
from app.features.communication import (
    CommunicationFacade,
    ConversationAccessResult,
    MessageResult,
    PreparedUserMessageResult,
    RecordedElfieMessageResult,
)
from app.orchestration.message_delivery import (
    DeliverElfieReplyCommand,
    DeliveryAdmission,
    DuplicateMessage,
    LiveConversationMessage,
    MessageDeliveryFacade,
    SubmitUserMessageCommand,
    UserMessageDeliveryAttempt,
)


def _principal() -> AccountPrincipal:
    return AccountPrincipal(7, "owner", "owner", "chat")


def _message(sender: str = "user") -> MessageResult:
    return MessageResult(
        id=1,
        elfie_id="00000001",
        sender=sender,  # type: ignore[arg-type]
        text="你好",
        created_at="2026-08-11T00:00:00.000Z",
    )


def _communication(events: list[str]) -> MagicMock:
    communication = MagicMock(spec=CommunicationFacade)
    access = ConversationAccessResult("00000001", 7, "owner")
    communication.prepare_user_message.side_effect = lambda *_args: (
        events.append("authorize")
        or PreparedUserMessageResult(
            access=access,
            text="你好",
            channel="web",
            message_id=None,
        )
    )
    communication.record_prepared_user_message.side_effect = lambda *_args: (
        events.append("persist") or _message()
    )
    communication.record_elfie_message.side_effect = lambda *_args: (
        events.append("persist_reply")
        or RecordedElfieMessageResult(owner_user_id=7, message=_message("elfie"))
    )
    return communication


class Delivery:
    def __init__(self, events: list[str], admission: DeliveryAdmission) -> None:
        self.events = events
        self.admission = admission
        self.attempts: list[UserMessageDeliveryAttempt] = []

    def deliver_user_message(
        self, attempt: UserMessageDeliveryAttempt
    ) -> DeliveryAdmission:
        self.events.append("deliver")
        self.attempts.append(attempt)
        return self.admission


class Live:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.messages: list[LiveConversationMessage] = []

    def publish_message(self, message: LiveConversationMessage) -> None:
        self.events.append("broadcast")
        self.messages.append(message)


def test_user_message_is_written_once_only_after_accepted_receipt() -> None:
    events: list[str] = []
    communication = _communication(events)
    delivery = Delivery(events, DeliveryAdmission(status="accepted"))
    facade = MessageDeliveryFacade(communication, delivery, Live(events))

    result = facade.submit_user_message(
        _principal(),
        SubmitUserMessageCommand(elfie_id="00000001", text="你好"),
    )

    assert result.message.text == "你好"
    assert events == ["authorize", "deliver", "persist"]
    communication.record_prepared_user_message.assert_called_once()


def test_external_channel_preserves_conversation_and_routes_through_same_channel() -> (
    None
):
    events: list[str] = []
    communication = _communication(events)
    communication.prepare_user_message.side_effect = None
    communication.prepare_user_message.return_value = PreparedUserMessageResult(
        access=ConversationAccessResult("00000001", 7, "owner"),
        text="你好",
        channel="telegram",
        message_id="telegram:991:update:42",
        conversation_id="telegram:1701",
        external_actor_id="701",
        external_actor_display_name="七号主人",
    )
    delivery = Delivery(events, DeliveryAdmission(status="accepted"))
    facade = MessageDeliveryFacade(communication, delivery, Live(events))

    facade.submit_user_message(
        _principal(),
        SubmitUserMessageCommand(
            elfie_id="00000001",
            text="你好",
            channel="telegram",
            conversation_id="telegram:1701",
            external_message_id="telegram:991:update:42",
            external_actor_id="701",
            external_actor_display_name="七号主人",
        ),
    )

    assert delivery.attempts[0].channel_id == "telegram"
    assert delivery.attempts[0].conversation_id == "telegram:1701"


def test_duplicate_receipt_does_not_write_history() -> None:
    events: list[str] = []
    communication = _communication(events)
    facade = MessageDeliveryFacade(
        communication,
        Delivery(events, DeliveryAdmission(status="duplicate")),
        Live(events),
    )

    with pytest.raises(DuplicateMessage):
        facade.submit_user_message(
            _principal(),
            SubmitUserMessageCommand(elfie_id="00000001", text="你好"),
        )

    assert events == ["authorize", "deliver"]
    communication.record_prepared_user_message.assert_not_called()


def test_elfie_reply_is_persisted_before_the_same_record_is_broadcast() -> None:
    events: list[str] = []
    communication = _communication(events)
    live = Live(events)
    facade = MessageDeliveryFacade(
        communication,
        Delivery(events, DeliveryAdmission(status="accepted")),
        live,
    )

    facade.deliver_elfie_reply(
        DeliverElfieReplyCommand(elfie_id="00000001", text="你好"),
    )

    assert events == ["persist_reply", "broadcast"]
    assert live.messages[0].message.id == 1
