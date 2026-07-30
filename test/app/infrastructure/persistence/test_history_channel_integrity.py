"""Final history cross-channel and membership integrity tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.infrastructure.persistence.history_schema import create_history_schema
from test.app.infrastructure.persistence.history_test_support import (
    assert_integrity_error,
    insert_conversation_fixture,
    insert_participants,
)


def test_rejects_cross_channel_participant_and_offset(tmp_path: Path) -> None:
    """Given web conversation, When sms bindings are inserted, Then they fail."""
    # Given
    db_path = tmp_path / "history.sqlite"
    create_history_schema(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_conversation_fixture(connection)
        connection.execute(
            "INSERT INTO self_channel_accounts VALUES "
            "('self_sms','sms','elfie:1','Elfie','active','{}','t0','t0')"
        )
        connection.execute(
            "INSERT INTO external_channel_accounts VALUES "
            "('external_sms',NULL,'sms','user:1','Owner','{}','t0',NULL,'t0')"
        )

        # When / Then
        assert_integrity_error(
            connection,
            "INSERT INTO conversation_participants VALUES "
            "('conv_1','external',NULL,'external_sms','Owner','owner','t0',NULL)",
        )
        assert_integrity_error(
            connection,
            "INSERT INTO ingestion_offsets VALUES "
            "('offset_1','sms','self_1','thread_1','c1','t0','{}')",
        )


def test_rejects_nonmember_external_sender(tmp_path: Path) -> None:
    """Given an external nonmember, When it sends directly, Then insertion fails."""
    # Given
    db_path = tmp_path / "history.sqlite"
    create_history_schema(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_conversation_fixture(connection)
        insert_participants(connection)

        # When / Then
        assert_integrity_error(
            connection,
            "INSERT INTO messages VALUES "
            "('msg_bad','conv_1','web','source_bad','external',NULL,'external_2',"
            "'inbound','text','bad','t0','t0',NULL,'{}')",
        )


def test_rejects_self_participant_that_is_not_conversation_owner(
    tmp_path: Path,
) -> None:
    """Given a second self account, When added as self, Then ownership fails."""
    # Given
    db_path = tmp_path / "history.sqlite"
    create_history_schema(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_conversation_fixture(connection)
        connection.execute(
            "INSERT INTO self_channel_accounts VALUES "
            "('self_2','web','elfie:2','Other','active','{}','t0','t0')"
        )

        # When / Then
        assert_integrity_error(
            connection,
            "INSERT INTO conversation_participants VALUES "
            "('conv_1','self','self_2',NULL,'Other','self','t0',NULL)",
        )


def test_rejects_message_update_to_nonmember_sender(tmp_path: Path) -> None:
    """Given a valid self message, When sender becomes a nonmember, Then it fails."""
    # Given
    db_path = tmp_path / "history.sqlite"
    create_history_schema(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_conversation_fixture(connection)
        insert_participants(connection)
        connection.execute(
            "INSERT INTO messages VALUES "
            "('msg_1','conv_1','web','s1','self','self_1',NULL,'outbound',"
            "'text','ok','t0','t0',NULL,'{}')"
        )

        # When / Then
        assert_integrity_error(
            connection,
            "UPDATE messages SET sender_type='external', self_account_id=NULL, "
            "channel_account_id='external_2', direction='inbound' "
            "WHERE message_id='msg_1'",
        )
