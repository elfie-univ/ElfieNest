"""Final history message, reply, JSON, and attachment path tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from infrastructure.persistence.nest_db.history_schema import create_history_schema
from test.infrastructure.persistence.history_test_support import (
    assert_integrity_error,
    insert_conversation_fixture,
    insert_participants,
    insert_self_message,
)


def test_commits_valid_message_attachment_and_offset(tmp_path: Path) -> None:
    """Given valid members, When chat rows are inserted, Then they commit."""
    # Given
    db_path = tmp_path / "history.sqlite"
    create_history_schema(db_path)

    # When
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_conversation_fixture(connection)
        insert_participants(connection)
        insert_self_message(connection)
        connection.execute(
            "INSERT INTO attachments VALUES "
            "('att_1','msg_1','image','a.png','image/png','attachments/a.png',"
            "NULL,12,'abc','{}','t0')"
        )
        connection.execute(
            "INSERT INTO ingestion_offsets VALUES "
            "('offset_1','web','self_1','thread_1','c1','t0','{}')"
        )

    # Then
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM messages").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM attachments").fetchone() == (1,)


def test_rejects_sender_direction_reply_and_json_bypasses(tmp_path: Path) -> None:
    """Given a valid chat, When invalid message rows enter, Then each fails."""
    # Given
    db_path = tmp_path / "history.sqlite"
    create_history_schema(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_conversation_fixture(connection)
        insert_participants(connection)
        insert_self_message(connection)

        # When / Then
        for statement in (
            "INSERT INTO messages VALUES ('bad_dir','conv_1','web','s1','self',"
            "'self_1',NULL,'inbound','text','x','t0','t0',NULL,'{}')",
            "INSERT INTO messages VALUES ('bad_reply','conv_1','web','s2','self',"
            "'self_1',NULL,'outbound','text','x','t0','t0','missing','{}')",
            "INSERT INTO messages VALUES ('bad_json','conv_1','web','s3','self',"
            "'self_1',NULL,'outbound','text','x','t0','t0',NULL,'[]')",
        ):
            assert_integrity_error(connection, statement)


def test_rejects_reply_to_message_in_another_conversation(tmp_path: Path) -> None:
    """Given messages in two conversations, When reply crosses them, Then it fails."""
    # Given
    db_path = tmp_path / "history.sqlite"
    create_history_schema(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_conversation_fixture(connection)
        insert_self_message(connection)
        connection.execute(
            "INSERT INTO conversations VALUES "
            "('conv_2','web','thread_2','direct',NULL,'self_1','t0',NULL,'active','{}')"
        )
        connection.execute(
            "INSERT INTO messages VALUES "
            "('msg_2','conv_2','web','source_2','self','self_1',NULL,'outbound',"
            "'text','other','t0','t0',NULL,'{}')"
        )

        # When / Then
        assert_integrity_error(
            connection,
            "INSERT INTO messages VALUES "
            "('bad_cross','conv_1','web','source_cross','self','self_1',NULL,"
            "'outbound','text','bad','t0','t0','msg_2','{}')",
        )


def test_rejects_unsafe_attachment_paths(tmp_path: Path) -> None:
    """Given a valid message, When unsafe local paths enter, Then each fails."""
    # Given
    db_path = tmp_path / "history.sqlite"
    create_history_schema(db_path)
    unsafe_paths = ("/tmp/a", "../a", "attachments/..", "C:\\a", "file://a")

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        insert_conversation_fixture(connection)
        insert_self_message(connection)

        # When / Then
        for index, unsafe_path in enumerate(unsafe_paths):
            statement = (
                "INSERT INTO attachments VALUES "
                f"('att_{index}','msg_1','file',NULL,NULL,'{unsafe_path}',"
                "NULL,0,NULL,'{}','t0')"
            )
            assert_integrity_error(connection, statement)
