"""History v2 message, attachment, and offset schema tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.infrastructure.persistence.history_v2_schema import create_history_v2_schema
from test.app.infrastructure.persistence.history_v2_test_support import (
    assert_integrity_error,
    business_tables,
    count_rows,
    indexes,
    insert_conversation_fixture,
    insert_self_message,
)


def test_creates_exact_final_seven_business_tables(tmp_path: Path) -> None:
    """Given an explicit v2 path, When initialized, Then final chat tables exist."""
    # Given
    db_path = tmp_path / "history_v2.sqlite"

    # When
    create_history_v2_schema(db_path)

    # Then
    assert business_tables(db_path) == [
        "attachments",
        "conversation_participants",
        "conversations",
        "external_channel_accounts",
        "ingestion_offsets",
        "messages",
        "self_channel_accounts",
    ]


def test_commits_message_attachment_and_ingestion_offset_together(
    tmp_path: Path,
) -> None:
    """Given valid conversation rows, When v2 message data is inserted, Then it commits."""
    # Given
    db_path = tmp_path / "history_v2.sqlite"
    create_history_v2_schema(db_path)

    # When
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_conversation_fixture(connection)
        insert_self_message(connection, message_id="msg_1", reply_to_message_id=None)
        insert_self_message(
            connection, message_id="msg_2", reply_to_message_id="msg_1"
        )
        connection.execute(
            """
            INSERT INTO attachments (
                attachment_id, message_id, kind, filename, mime_type, local_path,
                external_url, size_bytes, sha256, meta_json, created_at
            ) VALUES (
                'att_1', 'msg_1', 'image', 'a.png', 'image/png',
                'attachments/a.png', NULL, 12, 'abc', '{}', '2026-07-29T00:00:00Z'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO attachments (
                attachment_id, message_id, kind, filename, mime_type, local_path,
                external_url, size_bytes, sha256, meta_json, created_at
            ) VALUES (
                'att_2', 'msg_1', 'note', NULL, NULL,
                NULL, NULL, NULL, NULL, '{"legacy_ref": true}', '2026-07-29T00:00:00Z'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO ingestion_offsets (
                offset_id, channel, self_account_id, external_thread_id, cursor,
                last_synced_at, meta_json
            ) VALUES (
                'offset_1', 'web', 'self_1', 'thread_1', 'cursor-1',
                '2026-07-29T00:00:00Z', '{}'
            )
            """
        )

    # Then
    assert count_rows(db_path, "messages") == 2
    assert count_rows(db_path, "attachments") == 2
    assert count_rows(db_path, "ingestion_offsets") == 1


def test_rejects_invalid_message_sender_source_key_and_reply(
    tmp_path: Path,
) -> None:
    """Given invalid message rows, When inserted, Then message constraints reject them."""
    # Given
    db_path = tmp_path / "history_v2.sqlite"
    create_history_v2_schema(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_conversation_fixture(connection)
        insert_self_message(connection, message_id="msg_1", reply_to_message_id=None)

        # When / Then
        assert_integrity_error(
            connection,
            """
            INSERT INTO messages (
                message_id, conversation_id, channel, source_message_key, sender_type,
                self_account_id, channel_account_id, direction, message_type, text,
                created_at, ingested_at, reply_to_message_id, meta_json
            ) VALUES (
                'msg_bad_sender', 'conv_1', 'web', 'source_bad_sender', 'self',
                'self_1', 'external_1', 'outbound', 'text', 'bad',
                '2026-07-29T00:00:00Z', '2026-07-29T00:00:00Z', NULL, '{}'
            )
            """,
        )
        assert_integrity_error(
            connection,
            """
            INSERT INTO messages (
                message_id, conversation_id, channel, source_message_key, sender_type,
                self_account_id, channel_account_id, direction, message_type, text,
                created_at, ingested_at, reply_to_message_id, meta_json
            ) VALUES (
                'msg_duplicate_source', 'conv_1', 'web', 'source_msg_1', 'self',
                'self_1', NULL, 'outbound', 'text', 'duplicate',
                '2026-07-29T00:00:00Z', '2026-07-29T00:00:00Z', NULL, '{}'
            )
            """,
        )
        assert_integrity_error(
            connection,
            """
            INSERT INTO messages (
                message_id, conversation_id, channel, source_message_key, sender_type,
                self_account_id, channel_account_id, direction, message_type, text,
                created_at, ingested_at, reply_to_message_id, meta_json
            ) VALUES (
                'msg_bad_reply', 'conv_1', 'web', 'source_bad_reply', 'self',
                'self_1', NULL, 'outbound', 'text', 'bad reply',
                '2026-07-29T00:00:00Z', '2026-07-29T00:00:00Z', 'missing', '{}'
            )
            """,
        )
        assert_integrity_error(
            connection,
            """
            INSERT INTO messages (
                message_id, conversation_id, channel, source_message_key, sender_type,
                self_account_id, channel_account_id, direction, message_type, text,
                created_at, ingested_at, reply_to_message_id, meta_json
            ) VALUES (
                'msg_bad_json', 'conv_1', 'web', 'source_bad_json', 'self',
                'self_1', NULL, 'outbound', 'text', 'bad json',
                '2026-07-29T00:00:00Z', '2026-07-29T00:00:00Z', NULL, 'not-json'
            )
            """,
        )


def test_rejects_invalid_attachment_and_offset_rows(tmp_path: Path) -> None:
    """Given invalid attachment and offset rows, When inserted, Then constraints fail."""
    # Given
    db_path = tmp_path / "history_v2.sqlite"
    create_history_v2_schema(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_conversation_fixture(connection)
        insert_self_message(connection, message_id="msg_1", reply_to_message_id=None)
        connection.execute(
            """
            INSERT INTO ingestion_offsets VALUES (
                'offset_1', 'web', 'self_1', 'thread_1', 'cursor-1',
                '2026-07-29T00:00:00Z', '{}'
            )
            """
        )

        # When / Then
        assert_integrity_error(
            connection,
            """
            INSERT INTO attachments VALUES (
                'att_absolute', 'msg_1', 'image', 'a.png', 'image/png',
                '/tmp/a.png', NULL, 12, NULL, '{}', '2026-07-29T00:00:00Z'
            )
            """,
        )
        assert_integrity_error(
            connection,
            """
            INSERT INTO attachments VALUES (
                'att_both', 'msg_1', 'image', 'a.png', 'image/png',
                'attachments/a.png', 'https://example.test/a.png', 12, NULL, '{}',
                '2026-07-29T00:00:00Z'
            )
            """,
        )
        assert_integrity_error(
            connection,
            """
            INSERT INTO attachments VALUES (
                'att_negative', 'msg_1', 'image', 'a.png', 'image/png',
                NULL, NULL, -1, NULL, '{}', '2026-07-29T00:00:00Z'
            )
            """,
        )
        assert_integrity_error(
            connection,
            """
            INSERT INTO ingestion_offsets VALUES (
                'offset_duplicate', 'web', 'self_1', 'thread_1', 'cursor-2',
                '2026-07-29T00:01:00Z', '{}'
            )
            """,
        )


def test_exposes_required_message_query_indexes(tmp_path: Path) -> None:
    """Given initialized schema, When indexes are inspected, Then query indexes exist."""
    # Given
    db_path = tmp_path / "history_v2.sqlite"

    # When
    create_history_v2_schema(db_path)

    # Then
    assert set(indexes(db_path, "messages")) >= {
        "idx_messages_conversation_created",
        "idx_messages_reply_to_message",
        "idx_messages_sender_self",
    }
    assert set(indexes(db_path, "attachments")) >= {
        "idx_attachments_message_id",
    }
    assert set(indexes(db_path, "ingestion_offsets")) >= {
        "idx_ingestion_offsets_self_account",
    }
