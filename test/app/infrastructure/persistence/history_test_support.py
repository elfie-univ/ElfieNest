"""Shared direct-SQL fixtures for final history schema tests."""

from __future__ import annotations

import sqlite3


def insert_conversation_fixture(connection: sqlite3.Connection) -> None:
    """Insert one self account, two external accounts, and one conversation."""
    connection.execute(
        "INSERT INTO self_channel_accounts VALUES "
        "('self_1','web','elfie:00000001','Elfie','active','{}','t0','t0')"
    )
    connection.execute(
        "INSERT INTO external_channel_accounts VALUES "
        "('external_1',NULL,'web','user:1','Owner','{}','t0',NULL,'t0')"
    )
    connection.execute(
        "INSERT INTO external_channel_accounts VALUES "
        "('external_2',NULL,'web','user:2','Other','{}','t0',NULL,'t0')"
    )
    connection.execute(
        "INSERT INTO conversations VALUES "
        "('conv_1','web','thread_1','direct',NULL,'self_1','t0',NULL,'active','{}')"
    )


def insert_participants(connection: sqlite3.Connection) -> None:
    """Insert the owner and first external account as active participants."""
    connection.execute(
        "INSERT INTO conversation_participants VALUES "
        "('conv_1','self','self_1',NULL,'Elfie','self','t0',NULL)"
    )
    connection.execute(
        "INSERT INTO conversation_participants VALUES "
        "('conv_1','external',NULL,'external_1','Owner','owner','t0',NULL)"
    )


def insert_self_message(connection: sqlite3.Connection, message_id: str = "msg_1") -> None:
    """Insert one valid outbound self message."""
    connection.execute(
        """
        INSERT INTO messages VALUES (
            ?, 'conv_1', 'web', ?, 'self', 'self_1', NULL, 'outbound',
            'text', 'hello', 't0', 't0', NULL, '{}'
        )
        """,
        (message_id, f"source_{message_id}"),
    )


def assert_integrity_error(connection: sqlite3.Connection, statement: str) -> None:
    """Assert one adversarial direct-SQL statement is rejected."""
    try:
        connection.execute(statement)
    except sqlite3.IntegrityError:
        return
    raise AssertionError("expected sqlite3.IntegrityError")
