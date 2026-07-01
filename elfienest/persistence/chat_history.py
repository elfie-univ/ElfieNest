from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import sqlite3
from typing import assert_never

from elfienest.persistence.store import get_db


class ChatSender(StrEnum):
    USER = "user"
    ELFIE = "elfie"
    SYSTEM = "system"


class ChatHistoryRange(StrEnum):
    ALL = "all"
    LAST_15_MINUTES = "15m"
    LAST_HOUR = "1h"
    TODAY = "today"


@dataclass(frozen=True, slots=True)
class ChatMessageInput:
    elfie_id: str
    user_id: int
    sender: ChatSender
    text: str
    meta: str = ""
    created_at: str | None = None


@dataclass(frozen=True, slots=True)
class ChatHistoryQuery:
    elfie_id: str
    user_id: int
    history_range: ChatHistoryRange = ChatHistoryRange.ALL
    keyword: str = ""
    limit: int = 100
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class ChatMessageRecord:
    id: int
    elfie_id: str
    user_id: int
    sender: str
    text: str
    meta: str
    created_at: str


def record_chat_message(db_path: str, message: ChatMessageInput) -> ChatMessageRecord:
    created_at = message.created_at or _utc_now_iso()
    with get_db(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO chat_messages "
            "(elfie_id, user_id, sender, text, meta, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                message.elfie_id,
                message.user_id,
                message.sender.value,
                message.text,
                message.meta,
                created_at,
            ),
        )
        message_id = int(cursor.lastrowid)
        conn.commit()
        row = conn.execute(
            "SELECT id, elfie_id, user_id, sender, text, meta, created_at "
            "FROM chat_messages WHERE id = ?",
            (message_id,),
        ).fetchone()
    return _row_to_record(row)


def list_chat_history(db_path: str, query: ChatHistoryQuery) -> list[ChatMessageRecord]:
    clauses = ["elfie_id = ?", "user_id = ?"]
    params: list[str | int] = [query.elfie_id, query.user_id]

    start = _range_start(query.history_range, query.now or datetime.now(UTC))
    if start:
        clauses.append("created_at >= ?")
        params.append(start)

    keyword = query.keyword.strip()
    if keyword:
        pattern = f"%{keyword}%"
        clauses.append("(text LIKE ? OR meta LIKE ? OR sender LIKE ?)")
        params.extend([pattern, pattern, pattern])

    limit = max(1, min(200, query.limit))
    params.append(limit)

    sql = (
        "SELECT id, elfie_id, user_id, sender, text, meta, created_at "
        "FROM chat_messages "
        f"WHERE {' AND '.join(clauses)} "
        "ORDER BY created_at ASC, id ASC "
        "LIMIT ?"
    )
    with get_db(db_path) as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [_row_to_record(row) for row in rows]


def _range_start(history_range: ChatHistoryRange, now: datetime) -> str | None:
    match history_range:
        case ChatHistoryRange.ALL:
            return None
        case ChatHistoryRange.LAST_15_MINUTES:
            return _datetime_to_iso(now - timedelta(minutes=15))
        case ChatHistoryRange.LAST_HOUR:
            return _datetime_to_iso(now - timedelta(hours=1))
        case ChatHistoryRange.TODAY:
            start = now.astimezone(UTC).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            return _datetime_to_iso(start)
        case _ as unreachable:
            assert_never(unreachable)


def _utc_now_iso() -> str:
    return _datetime_to_iso(datetime.now(UTC))


def _datetime_to_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _row_to_record(row: sqlite3.Row) -> ChatMessageRecord:
    return ChatMessageRecord(
        id=int(row["id"]),
        elfie_id=str(row["elfie_id"]),
        user_id=int(row["user_id"]),
        sender=str(row["sender"]),
        text=str(row["text"]),
        meta=str(row["meta"] or ""),
        created_at=str(row["created_at"]),
    )
