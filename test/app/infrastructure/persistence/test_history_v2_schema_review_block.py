"""Review-block regressions for history v2 schema."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.infrastructure.persistence.history_v2_schema import create_history_v2_schema
from test.app.infrastructure.persistence.history_v2_review_test_data import (
    array_json_rows,
    null_identity_rows,
)
from test.app.infrastructure.persistence.history_v2_test_support import (
    assert_integrity_error,
    assert_table_values_rejected,
    insert_attachment,
    insert_conversation_fixture,
    insert_self_message,
    table_columns,
)


def test_rejects_participant_type_account_mismatches(tmp_path: Path) -> None:
    """Given participant type mismatch rows, When inserted, Then checks reject them."""
    # Given
    db_path = tmp_path / "history_v2.sqlite"
    create_history_v2_schema(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_conversation_fixture(connection)

        # When / Then
        assert_integrity_error(
            connection,
            """
            INSERT INTO conversation_participants (
                conversation_id, participant_type, self_account_id,
                channel_account_id, display_name_snapshot, role, joined_at, left_at
            ) VALUES (
                'conv_1', 'self', NULL, 'external_1',
                'external as self', 'owner', '2026-07-29T00:00:00Z', NULL
            )
            """,
        )
        assert_integrity_error(
            connection,
            """
            INSERT INTO conversation_participants (
                conversation_id, participant_type, self_account_id,
                channel_account_id, display_name_snapshot, role, joined_at, left_at
            ) VALUES (
                'conv_1', 'external', 'self_1', NULL,
                'self as external', 'self', '2026-07-29T00:00:00Z', NULL
            )
            """,
        )


def test_rejects_unsafe_attachment_local_paths_but_allows_metadata_only(
    tmp_path: Path,
) -> None:
    """Given unsafe local refs, When inserted, Then only metadata-only is accepted."""
    # Given
    db_path = tmp_path / "history_v2.sqlite"
    create_history_v2_schema(db_path)
    unsafe_paths = (
        "attachments/..",
        "..\\escape.png",
        "daily\\..\\x",
        "C:\\escape.png",
        "\\\\server\\share\\x.png",
        "\\leading\\x.png",
        "/tmp/a.png",
        "file:///tmp/a.png",
        "https://example.test/a.png",
    )

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_conversation_fixture(connection)
        insert_self_message(connection, message_id="msg_1", reply_to_message_id=None)

        # When / Then
        insert_attachment(connection, attachment_id="metadata_only", local_path=None)
        for index, unsafe_path in enumerate(unsafe_paths):
            assert_integrity_error(
                connection,
                """
                INSERT INTO attachments (
                    attachment_id, message_id, kind, filename, mime_type, local_path,
                    external_url, size_bytes, sha256, meta_json, created_at
                ) VALUES (
                    ?, 'msg_1', 'image', 'a.png', 'image/png',
                    ?, NULL, 12, NULL, '{}', '2026-07-29T00:00:00Z'
                )
                """,
                (f"bad_path_{index}", unsafe_path),
            )


def test_identity_text_primary_keys_are_explicitly_not_null(
    tmp_path: Path,
) -> None:
    """Given final v2 tables, When inspected, Then identity TEXT keys reject NULL."""
    # Given
    db_path = tmp_path / "history_v2.sqlite"

    # When
    create_history_v2_schema(db_path)

    # Then
    expected_identity_columns = {
        "self_channel_accounts": "self_account_id",
        "external_channel_accounts": "channel_account_id",
        "conversations": "conversation_id",
        "messages": "message_id",
        "attachments": "attachment_id",
        "ingestion_offsets": "offset_id",
    }
    for table_name, column_name in expected_identity_columns.items():
        column_type, is_not_null = table_columns(db_path, table_name)[column_name]
        assert column_type == "TEXT"
        assert is_not_null is True

    assert table_columns(db_path, "conversation_participants")[
        "conversation_id"
    ] == ("TEXT", True)


def test_rejects_null_identity_keys_and_non_object_json(tmp_path: Path) -> None:
    """Given NULL identities or array JSON metadata, When inserted, Then checks fail."""
    # Given
    db_path = tmp_path / "history_v2.sqlite"
    create_history_v2_schema(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_conversation_fixture(connection)
        insert_self_message(connection, message_id="msg_1", reply_to_message_id=None)

        # When / Then
        for table_name, values in null_identity_rows():
            assert_table_values_rejected(connection, table_name, values)

        for table_name, values in array_json_rows():
            assert_table_values_rejected(connection, table_name, values)


def test_rejects_sender_direction_mismatches(tmp_path: Path) -> None:
    """Given sender/direction mismatch rows, When inserted, Then checks reject them."""
    # Given
    db_path = tmp_path / "history_v2.sqlite"
    create_history_v2_schema(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_conversation_fixture(connection)

        # When / Then
        for message_id, sender_type, self_id, external_id, direction in (
            ("msg_self_inbound", "self", "self_1", None, "inbound"),
            ("msg_external_outbound", "external", None, "external_1", "outbound"),
            ("msg_internal_outbound", "internal", None, None, "outbound"),
        ):
            assert_integrity_error(
                connection,
                """
                INSERT INTO messages (
                    message_id, conversation_id, channel, source_message_key,
                    sender_type, self_account_id, channel_account_id, direction,
                    message_type, text, created_at, ingested_at,
                    reply_to_message_id, meta_json
                ) VALUES (
                    ?, 'conv_1', 'web', ?, ?, ?, ?, ?, 'text', 'bad',
                    '2026-07-29T00:00:00Z', '2026-07-29T00:00:00Z', NULL, '{}'
                )
                """,
                (
                    message_id,
                    f"source_{message_id}",
                    sender_type,
                    self_id,
                    external_id,
                    direction,
                ),
            )
        assert_integrity_error(
            connection,
            """
            INSERT INTO attachments (
                attachment_id, message_id, kind, filename, mime_type, local_path,
                external_url, size_bytes, sha256, meta_json, created_at
            ) VALUES (
                NULL, 'msg_1', 'image', 'a.png', 'image/png',
                NULL, NULL, 12, NULL, '{}', '2026-07-29T00:00:00Z'
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
                'msg_json_array', 'conv_1', 'web', 'source_json_array', 'self',
                'self_1', NULL, 'outbound', 'text', 'bad',
                '2026-07-29T00:00:00Z', '2026-07-29T00:00:00Z', NULL, '[]'
            )
            """,
        )
