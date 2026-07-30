"""Shared fixtures for history v2 schema tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def business_tables(db_path: Path) -> list[str]:
    """Return non-SQLite internal table names."""
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    return [str(row[0]) for row in rows]


def indexes(db_path: Path, table_name: str) -> list[str]:
    """Return explicit indexes for one table."""
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'index' AND tbl_name = ? AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """,
            (table_name,),
        ).fetchall()
    return [str(row[0]) for row in rows]


def table_columns(db_path: Path, table_name: str) -> dict[str, tuple[str, bool]]:
    """Return column type and not-null flag keyed by column name."""
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]): (str(row[2]), bool(row[3])) for row in rows}


def insert_attachment(
    connection: sqlite3.Connection,
    *,
    attachment_id: str,
    local_path: str | None,
    external_url: str | None = None,
) -> None:
    """Insert an attachment row with configurable path fields."""
    connection.execute(
        """
        INSERT INTO attachments (
            attachment_id, message_id, kind, filename, mime_type, local_path,
            external_url, size_bytes, sha256, meta_json, created_at
        ) VALUES (
            ?, 'msg_1', 'image', 'a.png', 'image/png', ?, ?, 12, NULL, '{}',
            '2026-07-29T00:00:00Z'
        )
        """,
        (attachment_id, local_path, external_url),
    )


def count_rows(db_path: Path, table_name: str) -> int:
    """Count rows in a test-owned table name."""
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
    return int(row[0])


def assert_integrity_error(
    connection: sqlite3.Connection,
    statement: str,
    parameters: tuple[str | int | None, ...] = (),
) -> None:
    """Assert that one SQL statement fails with an integrity error."""
    try:
        connection.execute(statement, parameters)
    except sqlite3.IntegrityError:
        return
    raise AssertionError("expected sqlite3.IntegrityError")


def assert_table_values_rejected(
    connection: sqlite3.Connection,
    table_name: str,
    values: tuple[str | int | None, ...],
) -> None:
    """Assert that a full-row INSERT by VALUES fails with integrity error."""
    placeholders = ",".join("?" for _unused in values)
    assert_integrity_error(
        connection,
        f"INSERT INTO {table_name} VALUES ({placeholders})",
        values,
    )


def insert_conversation_fixture(connection: sqlite3.Connection) -> None:
    """Insert a valid self account, external account, and direct conversation."""
    connection.execute(
        """
        INSERT INTO self_channel_accounts VALUES (
            'self_1', 'web', 'elfie:00000001', 'Elfie', 'active',
            '{}', '2026-07-29T00:00:00Z', '2026-07-29T00:00:00Z'
        )
        """
    )
    connection.execute(
        """
        INSERT INTO external_channel_accounts VALUES (
            'external_1', NULL, 'web', 'user:1',
            'Owner', '{}', '2026-07-29T00:00:00Z', NULL, '2026-07-29T00:00:00Z'
        )
        """
    )
    connection.execute(
        """
        INSERT INTO conversations VALUES (
            'conv_1', 'web', 'thread_1', 'direct', NULL, 'self_1',
            '2026-07-29T00:00:00Z', NULL, 'active', '{}'
        )
        """
    )


def insert_self_message(
    connection: sqlite3.Connection,
    *,
    message_id: str,
    reply_to_message_id: str | None,
) -> None:
    """Insert a valid outbound self message."""
    connection.execute(
        """
        INSERT INTO messages (
            message_id, conversation_id, channel, source_message_key, sender_type,
            self_account_id, channel_account_id, direction, message_type, text,
            created_at, ingested_at, reply_to_message_id, meta_json
        ) VALUES (
            ?, 'conv_1', 'web', ?, 'self', 'self_1', NULL, 'outbound', 'text',
            'hello', '2026-07-29T00:00:00Z', '2026-07-29T00:00:00Z', ?, '{}'
        )
        """,
        (message_id, f"source_{message_id}", reply_to_message_id),
    )
