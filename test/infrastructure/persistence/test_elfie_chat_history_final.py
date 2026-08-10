"""Elfie chat adapter integration tests against the final seven-table store."""

from __future__ import annotations

import sqlite3
import stat
from datetime import datetime, timezone
from pathlib import Path

import pytest

from infrastructure.persistence.elfie_chat_history import (
    ElfieChatHistoryRange,
    ElfieChatMessageInput,
    ElfieChatSender,
    list_elfie_chat_history,
    record_elfie_chat_message,
)
from test.infrastructure.persistence.test_history_schema import EXPECTED_TABLES

EXPECTED_MESSAGE_COLUMNS = [
    "message_id",
    "conversation_id",
    "channel",
    "source_message_key",
    "sender_type",
    "self_account_id",
    "channel_account_id",
    "direction",
    "message_type",
    "text",
    "created_at",
    "ingested_at",
    "reply_to_message_id",
    "meta_json",
]


def _history_path(data_home: Path, elfie_id: str = "00000001") -> Path:
    return data_home / "elfies" / elfie_id / "conversations" / "history.sqlite"


def test_write_creates_only_final_tables_and_columns(tmp_path: Path) -> None:
    """Given an empty root, When a message is written, Then only final DDL exists."""
    # Given
    data_home = tmp_path / "nest"

    # When
    record_elfie_chat_message(
        "00000001",
        ElfieChatMessageInput(
            message_id="web:owner-1",
            conversation_id="owner:7",
            sender=ElfieChatSender.USER,
            text="hello",
            channel="web",
            user_id=7,
        ),
        data_home=data_home,
    )

    # Then
    db_path = _history_path(data_home)
    with sqlite3.connect(db_path) as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        columns = connection.execute("PRAGMA table_info(messages)").fetchall()
        metadata = str(
            connection.execute("SELECT meta_json FROM messages").fetchone()[0]
        )
    assert {str(row[0]) for row in tables} == EXPECTED_TABLES
    assert [str(row[1]) for row in columns] == EXPECTED_MESSAGE_COLUMNS
    assert stat.S_IMODE(db_path.stat().st_mode) == 0o600
    assert "legacy_" not in metadata


def test_sender_mapping_and_reopen_preserve_public_records(tmp_path: Path) -> None:
    """Given all public senders, When reopened, Then legacy DTO values survive."""
    # Given
    data_home = tmp_path / "nest"
    messages = (
        (ElfieChatSender.USER, "owner", 7),
        (ElfieChatSender.ELFIE, "elfie", 7),
        (ElfieChatSender.SYSTEM, "system", None),
    )

    # When
    for index, (sender, text, user_id) in enumerate(messages):
        record_elfie_chat_message(
            "00000001",
            ElfieChatMessageInput(
                message_id=f"web:{index}",
                conversation_id="owner:7",
                sender=sender,
                text=text,
                channel="web",
                created_at=f"2026-07-30T00:00:0{index}.000Z",
                user_id=user_id,
                meta=f"meta-{index}",
                attachment_refs=(f"sha256:ref-{index}",),
            ),
            data_home=data_home,
        )
    reopened = list_elfie_chat_history("00000001", "owner:7", data_home=data_home)
    user_history = list_elfie_chat_history(
        "00000001", "owner:7", user_id=7, data_home=data_home
    )

    # Then
    assert [record.sender for record in reopened] == [item[0] for item in messages]
    assert [record.sender for record in user_history] == [
        ElfieChatSender.USER,
        ElfieChatSender.ELFIE,
    ]
    assert [record.meta for record in reopened] == ["meta-0", "meta-1", "meta-2"]
    assert reopened[0].attachment_refs_json == '["sha256:ref-0"]'
    with sqlite3.connect(_history_path(data_home)) as connection:
        mappings = connection.execute(
            "SELECT sender_type, direction FROM messages ORDER BY created_at"
        ).fetchall()
    assert mappings == [
        ("external", "inbound"),
        ("self", "outbound"),
        ("internal", "internal"),
    ]


def test_final_database_rejects_sender_channel_and_attachment_bypasses(
    tmp_path: Path,
) -> None:
    """Given adapter fixtures, When final DDL is bypassed, Then invalid rows fail."""
    # Given
    data_home = tmp_path / "nest"
    record_elfie_chat_message(
        "00000001",
        ElfieChatMessageInput(
            message_id="web:1",
            conversation_id="owner:7",
            sender=ElfieChatSender.USER,
            text="hello",
            channel="web",
            user_id=7,
        ),
        data_home=data_home,
    )

    # When / Then
    with sqlite3.connect(_history_path(data_home)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        conversation_id = str(
            connection.execute("SELECT conversation_id FROM conversations").fetchone()[
                0
            ]
        )
        invalid_statements = (
            (
                "INSERT INTO messages VALUES "
                "('bad-sender',?,'web','bad-sender','self',NULL,NULL,"
                "'inbound','text','x','t0','t0',NULL,'{}')",
                (conversation_id,),
            ),
            (
                "INSERT INTO messages VALUES "
                "('bad-channel',?,'sms','bad-channel','internal',NULL,NULL,"
                "'internal','text','x','t0','t0',NULL,'{}')",
                (conversation_id,),
            ),
            (
                "INSERT INTO attachments VALUES "
                "('bad-path','web:1','file',NULL,NULL,'../secret',NULL,0,NULL,"
                "'{}','t0')",
                (),
            ),
        )
        for statement, parameters in invalid_statements:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement, parameters)


def test_combines_public_history_filters_on_final_rows(tmp_path: Path) -> None:
    """Given mixed rows, When all filters apply, Then only the limited match returns."""
    # Given
    data_home = tmp_path / "nest"
    fixtures = (
        ("old", "owner:7", 7, "2026-07-29T20:00:00.000Z"),
        ("first", "owner:7", 7, "2026-07-30T00:10:00.000Z"),
        ("second", "owner:7", 7, "2026-07-30T00:20:00.000Z"),
        ("other-conversation", "owner:8", 7, "2026-07-30T00:15:00.000Z"),
        ("other-user", "owner:7", 8, "2026-07-30T00:15:00.000Z"),
    )
    for message_id, conversation_id, user_id, created_at in fixtures:
        record_elfie_chat_message(
            "00000001",
            ElfieChatMessageInput(
                message_id=message_id,
                conversation_id=conversation_id,
                sender=ElfieChatSender.USER,
                text=f"needle {message_id}",
                channel="web",
                created_at=created_at,
                user_id=user_id,
            ),
            data_home=data_home,
        )

    # When
    records = list_elfie_chat_history(
        "00000001",
        "owner:7",
        user_id=7,
        history_range=ElfieChatHistoryRange.LAST_HOUR,
        keyword="needle",
        limit=1,
        now=datetime(2026, 7, 30, 1, 0, tzinfo=timezone.utc),
        data_home=data_home,
    )

    # Then
    assert [record.message_id for record in records] == ["first"]
