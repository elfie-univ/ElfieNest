from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.features.accounts import AccountPrincipal
from app.features.communication import (
    CommunicationFacade,
    ConversationMessageWrite,
    ConversationNotFound,
    ListConversationsQuery,
    ListMessagesQuery,
    RecordUserMessageCommand,
    StoredConversationMessage,
)
from app.features.elfies import ElfiesService


class MemoryHistory:
    def __init__(self) -> None:
        self.messages: list[StoredConversationMessage] = []
        self.writes: list[ConversationMessageWrite] = []

    def list_messages(
        self,
        elfie_id: str,
        *,
        conversation_id: str,
        user_id: int,
    ) -> tuple[StoredConversationMessage, ...]:
        assert elfie_id == "00000001"
        assert conversation_id == "owner:7"
        assert user_id == 7
        return tuple(self.messages)

    def append_message(
        self, message: ConversationMessageWrite
    ) -> StoredConversationMessage:
        self.writes.append(message)
        stored = StoredConversationMessage(
            id=len(self.messages) + 1,
            sender=message.sender,
            text=message.text,
            created_at="2026-08-11T00:00:00.000Z",
        )
        self.messages.append(stored)
        return stored

    def owner_user_id(self, elfie_id: str) -> int | None:
        return 7 if elfie_id == "00000001" else None


def _principal() -> AccountPrincipal:
    return AccountPrincipal(
        user_id=7,
        account_id="owner",
        role="owner",
        default_landing_page="chat",
    )


def _facade(history: MemoryHistory) -> CommunicationFacade:
    elfies = MagicMock(spec=ElfiesService)
    profile = SimpleNamespace(elfie_id="00000001", name="小白")
    elfies.list_visible.return_value = (SimpleNamespace(profile=profile),)
    elfies.get_profile.return_value = SimpleNamespace(profile=profile)
    return CommunicationFacade(history, elfies)


def test_conversation_directory_and_history_use_one_owner_scoped_port() -> None:
    history = MemoryHistory()
    history.messages.append(
        StoredConversationMessage(
            id=1,
            sender="user",
            text="今天好吗？",
            created_at="2026-08-11T00:00:00.000Z",
        )
    )
    facade = _facade(history)

    directory = facade.list_conversations(_principal(), ListConversationsQuery())
    messages = facade.list_messages(
        _principal(),
        ListMessagesQuery(elfie_id="00000001"),
    )

    assert directory.items[0].last_message_preview == "今天好吗？"
    assert messages.items[0].text == "今天好吗？"


def test_record_user_message_normalizes_and_appends_exactly_once() -> None:
    history = MemoryHistory()
    facade = _facade(history)

    result = facade.record_user_message(
        _principal(),
        RecordUserMessageCommand(
            elfie_id="00000001",
            text="  你好  ",
            channel="web",
        ),
    )

    assert result.text == "你好"
    assert len(history.writes) == 1
    assert history.writes[0].conversation_id == "owner:7"


def test_hidden_elfie_is_a_conversation_not_found() -> None:
    history = MemoryHistory()
    elfies = MagicMock(spec=ElfiesService)
    elfies.list_visible.return_value = ()
    facade = CommunicationFacade(history, elfies)

    with pytest.raises(ConversationNotFound):
        facade.list_messages(_principal(), ListMessagesQuery(elfie_id="00000009"))


def test_message_authorization_uses_directory_without_loading_cognition() -> None:
    history = MemoryHistory()
    elfies = MagicMock(spec=ElfiesService)
    profile = SimpleNamespace(elfie_id="00000001", name="小白")
    elfies.list_visible.return_value = (SimpleNamespace(profile=profile),)
    elfies.get_profile.side_effect = AssertionError("must not load cognition")
    facade = CommunicationFacade(history, elfies)

    facade.list_messages(_principal(), ListMessagesQuery(elfie_id="00000001"))

    elfies.get_profile.assert_not_called()
