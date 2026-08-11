"""Persist public Elfie chat DTOs in the final per-Elfie history store."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Final, Iterator

from infrastructure.persistence.data_home import get_elfie_conversations_dir
from infrastructure.persistence.elfie_chat_history_queries import (
    select_history_rows,
    select_source_message,
)
from infrastructure.persistence.elfie_chat_history_support import (
    ensure_chat_conversation,
)
from infrastructure.persistence.history_schema import (
    HISTORY_FILENAME,
    create_history_schema,
)
from infrastructure.persistence.sqlite_connection import app_sqlite_connection


class ElfieChatSender(str, Enum):
    """Public sender values consumed by existing chat clients."""

    USER = "user"
    ELFIE = "elfie"
    SYSTEM = "system"


class ElfieChatHistoryRange(str, Enum):
    """Public history time windows."""

    ALL = "all"
    LAST_15_MINUTES = "15m"
    LAST_HOUR = "1h"
    TODAY = "today"


@dataclass(frozen=True)
class ElfieChatPersistenceError(RuntimeError):
    """A committed chat source key could not be read back."""

    message_id: str

    def __str__(self) -> str:
        return f"精灵聊天消息写入后未找到记录: {self.message_id}"


@dataclass(frozen=True)
class ElfieChatMessageInput:
    """Immutable public message input shared by HTTP and WebSocket callers."""

    message_id: str
    conversation_id: str
    sender: ElfieChatSender
    text: str
    channel: str
    created_at: str | None = None
    user_id: int | None = None
    meta: str = ""
    attachment_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ElfieChatMessageRecord:
    """Public record shape retained while the backing schema changes."""

    id: int
    message_id: str
    conversation_id: str
    sender: ElfieChatSender
    text: str
    channel: str
    created_at: str
    user_id: int | None
    meta: str
    attachment_refs_json: str


_STORAGE_SENDERS: Final = {
    ElfieChatSender.USER: ("external", "inbound"),
    ElfieChatSender.ELFIE: ("self", "outbound"),
    ElfieChatSender.SYSTEM: ("internal", "internal"),
}
_PUBLIC_SENDERS: Final = {
    "external": ElfieChatSender.USER,
    "self": ElfieChatSender.ELFIE,
    "internal": ElfieChatSender.SYSTEM,
}


def record_elfie_chat_message(
    elfie_id: str,
    message: ElfieChatMessageInput,
    *,
    data_home: Path | None = None,
) -> ElfieChatMessageRecord:
    """Append once by channel/source key and return the stable public record."""
    created_at = message.created_at or _utc_now_iso()
    db_path = _history_path(elfie_id, data_home)
    create_history_schema(db_path)
    with _open_history(db_path) as connection:
        self_account_id, external_account_id, storage_conversation_id = (
            ensure_chat_conversation(
                connection,
                elfie_id=elfie_id,
                conversation_id=message.conversation_id,
                channel=message.channel,
                user_id=message.user_id,
                created_at=created_at,
                needs_external_account=(
                    message.sender is ElfieChatSender.USER
                    or message.user_id is not None
                ),
            )
        )
        sender_type, direction = _STORAGE_SENDERS[message.sender]
        connection.execute(
            """INSERT OR IGNORE INTO messages (
                   message_id, conversation_id, channel, source_message_key,
                   sender_type, self_account_id, channel_account_id, direction,
                   message_type, text, created_at, ingested_at, meta_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'text', ?, ?, ?, ?)""",
            (
                message.message_id,
                storage_conversation_id,
                message.channel,
                message.message_id,
                sender_type,
                self_account_id if message.sender is ElfieChatSender.ELFIE else None,
                external_account_id if message.sender is ElfieChatSender.USER else None,
                direction,
                message.text,
                created_at,
                _utc_now_iso(),
                _encode_meta(message),
            ),
        )
        connection.execute(
            """UPDATE conversations SET last_message_at =
                   CASE WHEN last_message_at IS NULL OR last_message_at < ?
                        THEN ? ELSE last_message_at END
               WHERE conversation_id = ?""",
            (created_at, created_at, storage_conversation_id),
        )
        connection.commit()
        row = select_source_message(connection, message.channel, message.message_id)
    if row is None:
        raise ElfieChatPersistenceError(message.message_id)
    return _row_to_record(row)


def list_elfie_chat_history(
    elfie_id: str,
    conversation_id: str | None = None,
    *,
    user_id: int | None = None,
    history_range: ElfieChatHistoryRange = ElfieChatHistoryRange.ALL,
    keyword: str = "",
    limit: int = 100,
    now: datetime | None = None,
    data_home: Path | None = None,
) -> list[ElfieChatMessageRecord]:
    """Read final messages through the unchanged public filters and ordering."""
    db_path = _history_path(elfie_id, data_home)
    if not db_path.exists():
        return []
    create_history_schema(db_path)
    range_start = _range_start(history_range, now or datetime.now(timezone.utc))
    with _open_history(db_path) as connection:
        rows = select_history_rows(
            connection,
            conversation_id=conversation_id,
            user_id=user_id,
            range_start=range_start,
            keyword=keyword,
            limit=limit,
        )
    return [_row_to_record(row) for row in rows]


def _row_to_record(row: sqlite3.Row) -> ElfieChatMessageRecord:
    metadata = json.loads(str(row["meta_json"]))
    user_id_value = metadata.get("user_id")
    attachment_refs = metadata.get("attachment_refs", [])
    return ElfieChatMessageRecord(
        id=int(row["id"]),
        message_id=str(row["message_id"]),
        conversation_id=str(row["external_thread_id"]),
        sender=_PUBLIC_SENDERS[str(row["sender_type"])],
        text=str(row["text"] or ""),
        channel=str(row["channel"]),
        created_at=str(row["created_at"]),
        user_id=int(user_id_value) if user_id_value is not None else None,
        meta=str(metadata.get("meta", "")),
        attachment_refs_json=json.dumps(attachment_refs, ensure_ascii=False),
    )


def _encode_meta(message: ElfieChatMessageInput) -> str:
    return json.dumps(
        {
            "attachment_refs": list(message.attachment_refs),
            "meta": message.meta,
            "user_id": message.user_id,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _history_path(elfie_id: str, data_home: Path | None) -> Path:
    default_dir = get_elfie_conversations_dir(elfie_id)
    conversations_dir = (
        default_dir
        if data_home is None
        else data_home / "elfies" / elfie_id / "conversations"
    )
    return conversations_dir / HISTORY_FILENAME


@contextmanager
def _open_history(db_path: Path) -> Iterator[sqlite3.Connection]:
    with app_sqlite_connection(db_path) as connection:
        yield connection


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _range_start(history_range: ElfieChatHistoryRange, now: datetime) -> str | None:
    if history_range is ElfieChatHistoryRange.ALL:
        return None
    if history_range is ElfieChatHistoryRange.LAST_15_MINUTES:
        return _datetime_to_iso(now - timedelta(minutes=15))
    if history_range is ElfieChatHistoryRange.LAST_HOUR:
        return _datetime_to_iso(now - timedelta(hours=1))
    start = now.astimezone(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return _datetime_to_iso(start)


def _datetime_to_iso(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
