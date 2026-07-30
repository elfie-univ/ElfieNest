"""History v2 schema contract tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.infrastructure.persistence.history_v2_schema import create_history_v2_schema


def test_creates_account_conversation_schema_when_path_is_explicit(
    tmp_path: Path,
) -> None:
    """Given an explicit v2 path, When initialized, Then account tables exist."""
    # Given
    db_path = tmp_path / "elfies" / "00000001" / "conversations" / "history_v2.sqlite"

    # When
    create_history_v2_schema(db_path)

    # Then
    assert db_path.is_file()
    assert not (db_path.parent / "history.sqlite").exists()
    assert set(_business_tables(db_path)) >= {
        "conversation_participants",
        "conversations",
        "external_channel_accounts",
        "self_channel_accounts",
    }
    assert _indexes(db_path, "conversation_participants") == [
        "idx_conversation_participants_external_unique",
        "idx_conversation_participants_self_unique",
    ]


def test_commits_direct_conversation_with_self_and_external_participants(
    tmp_path: Path,
) -> None:
    """Given valid account rows, When participants are inserted, Then commit works."""
    # Given
    db_path = tmp_path / "history_v2.sqlite"
    create_history_v2_schema(db_path)

    # When
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _insert_self_account(connection)
        _insert_external_account(connection)
        _insert_conversation(connection, conversation_type="direct")
        connection.execute(
            """
            INSERT INTO conversation_participants (
                conversation_id, participant_type, self_account_id,
                channel_account_id, display_name_snapshot, role, joined_at, left_at
            ) VALUES
                ('conv_1', 'self', 'self_1', NULL, 'Elfie', 'self', '2026-07-29T00:00:00Z', NULL),
                ('conv_1', 'external', NULL, 'external_1', 'Owner', 'owner', '2026-07-29T00:00:00Z', NULL)
            """
        )

    # Then
    assert _count_rows(db_path, "conversation_participants") == 2


def test_rejects_invalid_conversation_and_participant_accounts(
    tmp_path: Path,
) -> None:
    """Given invalid rows, When inserted, Then schema constraints reject them."""
    # Given
    db_path = tmp_path / "history_v2.sqlite"
    create_history_v2_schema(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _insert_self_account(connection)
        _insert_external_account(connection)
        _insert_conversation(connection, conversation_type="direct")

        # When / Then
        _assert_integrity_error(
            connection,
            """
            INSERT INTO conversations (
                conversation_id, channel, external_thread_id, conversation_type,
                title, self_account_id, started_at, last_message_at, status, meta_json
            ) VALUES (
                'conv_bad_type', 'web', 'thread_bad', 'broadcast',
                NULL, 'self_1', '2026-07-29T00:00:00Z', NULL, 'active', '{}'
            )
            """,
        )
        _assert_integrity_error(
            connection,
            """
            INSERT INTO conversation_participants (
                conversation_id, participant_type, self_account_id,
                channel_account_id, display_name_snapshot, role, joined_at, left_at
            ) VALUES (
                'conv_1', 'external', 'self_1', 'external_1',
                'invalid', 'owner', '2026-07-29T00:00:00Z', NULL
            )
            """,
        )
        _assert_integrity_error(
            connection,
            """
            INSERT INTO conversation_participants (
                conversation_id, participant_type, self_account_id,
                channel_account_id, display_name_snapshot, role, joined_at, left_at
            ) VALUES (
                'conv_1', 'external', NULL, NULL,
                'invalid', 'owner', '2026-07-29T00:00:00Z', NULL
            )
            """,
        )


def test_rejects_duplicate_participant_per_conversation_and_account(
    tmp_path: Path,
) -> None:
    """Given existing participants, When duplicates are inserted, Then indexes fail."""
    # Given
    db_path = tmp_path / "history_v2.sqlite"
    create_history_v2_schema(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _insert_self_account(connection)
        _insert_external_account(connection)
        _insert_conversation(connection, conversation_type="group")
        connection.execute(
            """
            INSERT INTO conversation_participants (
                conversation_id, participant_type, self_account_id,
                channel_account_id, display_name_snapshot, role, joined_at, left_at
            ) VALUES ('conv_1', 'self', 'self_1', NULL, 'Elfie', 'self', '2026-07-29T00:00:00Z', NULL)
            """
        )
        connection.execute(
            """
            INSERT INTO conversation_participants (
                conversation_id, participant_type, self_account_id,
                channel_account_id, display_name_snapshot, role, joined_at, left_at
            ) VALUES ('conv_1', 'external', NULL, 'external_1', 'Owner', 'owner', '2026-07-29T00:00:00Z', NULL)
            """
        )

        # When / Then
        _assert_integrity_error(
            connection,
            """
            INSERT INTO conversation_participants (
                conversation_id, participant_type, self_account_id,
                channel_account_id, display_name_snapshot, role, joined_at, left_at
            ) VALUES ('conv_1', 'self', 'self_1', NULL, 'Elfie again', 'self', '2026-07-29T00:00:01Z', NULL)
            """,
        )
        _assert_integrity_error(
            connection,
            """
            INSERT INTO conversation_participants (
                conversation_id, participant_type, self_account_id,
                channel_account_id, display_name_snapshot, role, joined_at, left_at
            ) VALUES ('conv_1', 'external', NULL, 'external_1', 'Owner again', 'owner', '2026-07-29T00:00:01Z', NULL)
            """,
        )


def _business_tables(db_path: Path) -> list[str]:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    return [str(row[0]) for row in rows]


def _indexes(db_path: Path, table_name: str) -> list[str]:
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


def _count_rows(db_path: Path, table_name: str) -> int:
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
    return int(row[0])


def _assert_integrity_error(connection: sqlite3.Connection, statement: str) -> None:
    try:
        connection.execute(statement)
    except sqlite3.IntegrityError:
        return
    raise AssertionError("expected sqlite3.IntegrityError")


def _insert_self_account(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO self_channel_accounts (
            self_account_id, channel, external_account_id, display_name, status,
            meta_json, created_at, updated_at
        ) VALUES (
            'self_1', 'web', 'elfie:00000001', 'Elfie', 'active',
            '{}', '2026-07-29T00:00:00Z', '2026-07-29T00:00:00Z'
        )
        """
    )


def _insert_external_account(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO external_channel_accounts (
            channel_account_id, knowledge_entity_id, channel, external_account_id,
            display_name, profile_json, first_seen_at, last_seen_at, updated_at
        ) VALUES (
            'external_1', NULL, 'web', 'user:1',
            'Owner', '{}', '2026-07-29T00:00:00Z', NULL, '2026-07-29T00:00:00Z'
        )
        """
    )


def _insert_conversation(
    connection: sqlite3.Connection, *, conversation_type: str
) -> None:
    connection.execute(
        """
        INSERT INTO conversations (
            conversation_id, channel, external_thread_id, conversation_type,
            title, self_account_id, started_at, last_message_at, status, meta_json
        ) VALUES (
            'conv_1', 'web', 'thread_1', ?, NULL, 'self_1',
            '2026-07-29T00:00:00Z', NULL, 'active', '{}'
        )
        """,
        (conversation_type,),
    )
