"""Adapter over the one authoritative per-Elfie conversation history store."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

from ai_runtime.storage.data_home import data_home_from_db_path
from app.features.communication import (
    CommunicationPortError,
    ConversationMessageWrite,
    StoredConversationMessage,
)
from app.infrastructure.persistence.elfie_chat_history import (
    ElfieChatMessageInput,
    ElfieChatSender,
    list_elfie_chat_history,
    record_elfie_chat_message,
)
from app.infrastructure.persistence.runtime_query_repository import (
    RuntimeQueryRepository,
)


class SQLiteConversationHistoryAdapter:
    """Use the existing history implementation without copying SQL or writes."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._data_home = data_home_from_db_path(self._db_path)

    def list_messages(
        self,
        elfie_id: str,
        *,
        conversation_id: str,
        user_id: int,
    ) -> tuple[StoredConversationMessage, ...]:
        try:
            records = list_elfie_chat_history(
                elfie_id,
                conversation_id=conversation_id,
                user_id=user_id,
                data_home=self._data_home,
            )
        except (OSError, RuntimeError, sqlite3.Error) as error:
            raise CommunicationPortError("Unable to read conversation history") from error
        return tuple(
            StoredConversationMessage(
                id=record.id,
                sender=record.sender.value,
                text=record.text,
                created_at=record.created_at,
            )
            for record in records
        )

    def append_message(
        self, message: ConversationMessageWrite
    ) -> StoredConversationMessage:
        try:
            stored = record_elfie_chat_message(
                message.elfie_id,
                ElfieChatMessageInput(
                    message_id=message.message_id or _new_message_id(message.channel),
                    conversation_id=message.conversation_id,
                    sender=ElfieChatSender(message.sender),
                    text=message.text,
                    channel=message.channel,
                    user_id=message.user_id,
                    meta=message.meta,
                ),
                data_home=self._data_home,
            )
        except (OSError, RuntimeError, sqlite3.Error, ValueError) as error:
            raise CommunicationPortError("Unable to append conversation message") from error
        return StoredConversationMessage(
            id=stored.id,
            sender=stored.sender.value,
            text=stored.text,
            created_at=stored.created_at,
        )

    def owner_user_id(self, elfie_id: str) -> int | None:
        try:
            return RuntimeQueryRepository(self._db_path).owner_id_for_elfie(elfie_id)
        except (OSError, RuntimeError, sqlite3.Error) as error:
            raise CommunicationPortError("Unable to resolve conversation owner") from error


def _new_message_id(channel: str) -> str:
    return f"{channel}:{uuid4().hex}"


__all__ = ("SQLiteConversationHistoryAdapter",)
