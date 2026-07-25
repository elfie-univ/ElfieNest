"""单精灵工作区的持久化聊天历史。"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Iterator

from ai_runtime.storage.data_home import get_elfie_conversations_dir


class ElfieChatSender(str, Enum):
    """精灵会话中可持久化的发送方类型。"""

    USER = "user"
    ELFIE = "elfie"
    SYSTEM = "system"


class ElfieChatHistoryRange(str, Enum):
    """精灵聊天历史的时间窗口。"""

    ALL = "all"
    LAST_15_MINUTES = "15m"
    LAST_HOUR = "1h"
    TODAY = "today"


@dataclass(frozen=True)
class ElfieChatPersistenceError(RuntimeError):
    """已提交的精灵聊天消息无法重新读取。"""

    message_id: str

    def __str__(self) -> str:
        return f"精灵聊天消息写入后未找到记录: {self.message_id}"


@dataclass(frozen=True)
class ElfieChatMessageInput:
    """写入精灵聊天历史的不可变消息。"""

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
    """精灵聊天历史中的已持久化消息。"""

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


def record_elfie_chat_message(
    elfie_id: str,
    message: ElfieChatMessageInput,
    *,
    data_home: Path | None = None,
) -> ElfieChatMessageRecord:
    """追加消息；对相同消息 ID 的重试返回原有记录。"""
    created_at = message.created_at or _utc_now_iso()
    attachment_refs_json = json.dumps(message.attachment_refs, ensure_ascii=False)
    with _open_history(elfie_id, data_home) as connection:
        _initialize_schema(connection)
        connection.execute(
            """
            INSERT OR IGNORE INTO messages (
                message_id, conversation_id, sender, text, channel, created_at,
                user_id, meta, attachment_refs_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.message_id,
                message.conversation_id,
                message.sender.value,
                message.text,
                message.channel,
                created_at,
                message.user_id,
                message.meta,
                attachment_refs_json,
            ),
        )
        connection.commit()
        row = connection.execute(
            """
            SELECT rowid AS id, message_id, conversation_id, sender, text, channel, created_at,
                   user_id, meta, attachment_refs_json
            FROM messages WHERE message_id = ?
            """,
            (message.message_id,),
        ).fetchone()
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
    """按时间顺序读取一只精灵的全部或指定会话消息。"""
    history_path = _history_path(elfie_id, data_home)
    if not history_path.exists():
        return []
    with _open_history(elfie_id, data_home) as connection:
        _initialize_schema(connection)
        clauses: list[str] = []
        parameters: list[str | int] = []
        if conversation_id is not None:
            clauses.append("conversation_id = ?")
            parameters.append(conversation_id)
        if user_id is not None:
            clauses.append("user_id = ?")
            parameters.append(user_id)
        range_start = _range_start(history_range, now or datetime.now(timezone.utc))
        if range_start is not None:
            clauses.append("created_at >= ?")
            parameters.append(range_start)
        normalized_keyword = keyword.strip()
        if normalized_keyword:
            pattern = f"%{normalized_keyword}%"
            clauses.append("(text LIKE ? OR meta LIKE ? OR sender LIKE ? OR channel LIKE ?)")
            parameters.extend((pattern, pattern, pattern, pattern))
        parameters.append(max(1, min(200, limit)))
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = connection.execute(
            f"""
            SELECT rowid AS id, message_id, conversation_id, sender, text, channel,
                   created_at, user_id, meta, attachment_refs_json
            FROM messages {where_clause}
            ORDER BY created_at ASC, message_id ASC LIMIT ?
            """,
            tuple(parameters),
        ).fetchall()
    return [_row_to_record(row) for row in rows]


def _history_path(elfie_id: str, data_home: Path | None) -> Path:
    default_conversations_dir = get_elfie_conversations_dir(elfie_id)
    if data_home is None:
        return default_conversations_dir / "history.sqlite"
    return data_home / "elfies" / elfie_id / "conversations" / "history.sqlite"


@contextmanager
def _open_history(
    elfie_id: str, data_home: Path | None
) -> Iterator[sqlite3.Connection]:
    history_path = _history_path(elfie_id, data_home)
    history_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    connection = sqlite3.connect(str(history_path))
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def _initialize_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            message_id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            sender TEXT NOT NULL CHECK(sender IN ('user', 'elfie', 'system')),
            text TEXT NOT NULL,
            channel TEXT NOT NULL,
            created_at TEXT NOT NULL,
            user_id INTEGER,
            meta TEXT NOT NULL DEFAULT '',
            attachment_refs_json TEXT NOT NULL DEFAULT '[]'
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_messages_conversation_time
        ON messages(conversation_id, created_at, message_id)
        """
    )


def _row_to_record(row: sqlite3.Row) -> ElfieChatMessageRecord:
    return ElfieChatMessageRecord(
        id=int(row["id"]),
        message_id=str(row["message_id"]),
        conversation_id=str(row["conversation_id"]),
        sender=ElfieChatSender(str(row["sender"])),
        text=str(row["text"]),
        channel=str(row["channel"]),
        created_at=str(row["created_at"]),
        user_id=int(row["user_id"]) if row["user_id"] is not None else None,
        meta=str(row["meta"]),
        attachment_refs_json=str(row["attachment_refs_json"]),
    )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
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
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )
