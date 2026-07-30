"""History v2 cross-channel and reply integrity tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.infrastructure.persistence.history_v2_schema import create_history_v2_schema
from test.app.infrastructure.persistence.history_v2_channel_test_data import (
    cross_channel_insert_statements,
    cross_channel_update_statements,
    same_channel_insert_bypass_statements,
    same_channel_update_bypass_statements,
)
from test.app.infrastructure.persistence.history_v2_channel_test_support import (
    insert_cross_channel_accounts,
    insert_external_message,
    insert_owner_and_external_participants,
    insert_same_channel_nonmember_accounts,
    insert_second_conversation_with_message,
)
from test.app.infrastructure.persistence.history_v2_test_support import (
    assert_integrity_error,
    count_rows,
    insert_conversation_fixture,
    insert_self_message,
)


def test_accepts_same_channel_reply_participants_message_and_offset(
    tmp_path: Path,
) -> None:
    """Given same-channel rows, When inserted directly, Then they commit."""
    # Given
    db_path = tmp_path / "history_v2.sqlite"
    create_history_v2_schema(db_path)

    # When
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_conversation_fixture(connection)
        connection.execute(
            """
            INSERT INTO conversation_participants VALUES (
                'conv_1', 'self', 'self_1', NULL, 'Elfie', 'self',
                '2026-07-29T00:00:00Z', NULL
            )
            """
        )
        insert_self_message(connection, message_id="msg_1", reply_to_message_id=None)
        insert_self_message(
            connection, message_id="msg_2", reply_to_message_id="msg_1"
        )
        connection.execute(
            """
            INSERT INTO ingestion_offsets VALUES (
                'offset_1', 'web', 'self_1', 'thread_1', 'cursor-1',
                '2026-07-29T00:00:00Z', '{}'
            )
            """
        )

    # Then
    assert count_rows(db_path, "messages") == 2
    assert count_rows(db_path, "ingestion_offsets") == 1


def test_accepts_owner_and_participant_message_senders(tmp_path: Path) -> None:
    """Given owner and participant rows, When messages are inserted, Then they commit."""
    # Given
    db_path = tmp_path / "history_v2.sqlite"
    create_history_v2_schema(db_path)

    # When
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_conversation_fixture(connection)
        insert_owner_and_external_participants(connection)
        insert_self_message(connection, message_id="msg_1", reply_to_message_id=None)
        insert_external_message(connection)

    # Then
    assert count_rows(db_path, "messages") == 2


def test_rejects_same_channel_membership_insert_bypass(tmp_path: Path) -> None:
    """Given same-channel nonmembers, When inserted, Then membership checks reject."""
    # Given
    db_path = tmp_path / "history_v2.sqlite"
    create_history_v2_schema(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_conversation_fixture(connection)
        insert_same_channel_nonmember_accounts(connection)
        insert_owner_and_external_participants(connection)

        # When / Then
        for statement in same_channel_insert_bypass_statements():
            assert_integrity_error(connection, statement)


def test_rejects_same_channel_membership_update_bypass(tmp_path: Path) -> None:
    """Given valid rows, When updated to same-channel nonmembers, Then checks reject."""
    # Given
    db_path = tmp_path / "history_v2.sqlite"
    create_history_v2_schema(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_conversation_fixture(connection)
        insert_same_channel_nonmember_accounts(connection)
        insert_owner_and_external_participants(connection)
        insert_self_message(connection, message_id="msg_1", reply_to_message_id=None)
        insert_external_message(connection)

        # When / Then
        for statement in same_channel_update_bypass_statements():
            assert_integrity_error(connection, statement)


def test_rejects_cross_channel_insert_bindings(tmp_path: Path) -> None:
    """Given cross-channel rows, When inserted directly, Then constraints reject them."""
    # Given
    db_path = tmp_path / "history_v2.sqlite"
    create_history_v2_schema(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_conversation_fixture(connection)
        insert_cross_channel_accounts(connection)
        insert_self_message(connection, message_id="msg_1", reply_to_message_id=None)

        # When / Then
        for statement in cross_channel_insert_statements():
            assert_integrity_error(connection, statement)


def test_rejects_cross_channel_update_bindings(tmp_path: Path) -> None:
    """Given valid rows, When updated across channels, Then constraints reject them."""
    # Given
    db_path = tmp_path / "history_v2.sqlite"
    create_history_v2_schema(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_conversation_fixture(connection)
        insert_cross_channel_accounts(connection)
        connection.execute(
            """
            INSERT INTO conversation_participants VALUES (
                'conv_1', 'self', 'self_1', NULL, 'Elfie', 'self',
                '2026-07-29T00:00:00Z', NULL
            )
            """
        )
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
        for statement in cross_channel_update_statements():
            assert_integrity_error(connection, statement)


def test_rejects_cross_conversation_reply_insert_and_update(tmp_path: Path) -> None:
    """Given another conversation, When reply crosses it, Then constraints reject it."""
    # Given
    db_path = tmp_path / "history_v2.sqlite"
    create_history_v2_schema(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_conversation_fixture(connection)
        insert_self_message(connection, message_id="msg_1", reply_to_message_id=None)
        insert_second_conversation_with_message(connection)

        # When / Then
        assert_integrity_error(
            connection,
            """
            INSERT INTO messages VALUES (
                'msg_cross_reply', 'conv_1', 'web', 'source_cross_reply',
                'self', 'self_1', NULL, 'outbound', 'text', 'bad',
                '2026-07-29T00:00:00Z', '2026-07-29T00:00:00Z', 'msg_other', '{}'
            )
            """,
        )
        assert_integrity_error(
            connection,
            "UPDATE messages SET reply_to_message_id = 'msg_other' WHERE message_id = 'msg_1'",
        )
