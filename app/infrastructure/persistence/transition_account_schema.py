"""Explicit transition DDL for Card 7 root account storage."""

from __future__ import annotations

import sqlite3


def ensure_account_transition_schema(connection: sqlite3.Connection) -> None:
    """Create Card 7 transition tables without touching normal initialization."""
    ensure_final_user_columns(connection)
    ensure_session_transition_schema(connection)
    ensure_local_installations_schema(connection)


def ensure_session_transition_schema(connection: sqlite3.Connection) -> None:
    """Create the hash-only session table without reading legacy sessions."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions_v2 (
            token_hash TEXT NOT NULL PRIMARY KEY
                CHECK(length(token_hash) = 64
                    AND token_hash NOT GLOB '*[^0-9a-f]*'),
            user_id INTEGER NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            revoked_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_v2_user ON sessions_v2(user_id)"
    )


def ensure_local_installations_schema(connection: sqlite3.Connection) -> None:
    """Create only the final local Setup installation table and its index."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS local_installations (
            installation_id TEXT NOT NULL PRIMARY KEY CHECK(installation_id = 'local'),
            owner_user_id INTEGER,
            device_name TEXT,
            platform TEXT,
            machine_id_hash TEXT,
            setup_state TEXT NOT NULL DEFAULT 'not_started'
                CHECK(setup_state IN ('not_started', 'in_progress', 'completed')),
            setup_step TEXT NOT NULL DEFAULT 'not_started'
                CHECK(setup_step IN (
                    'not_started', 'owner', 'providers', 'nest', 'food'
                )),
            owner_completed_at TEXT,
            providers_completed_at TEXT,
            nest_completed_at TEXT,
            food_completed_at TEXT,
            completed_at TEXT,
            last_seen_at TEXT,
            active_task_step INTEGER CHECK(
                active_task_step IS NULL OR active_task_step BETWEEN 1 AND 5
            ),
            active_task_key TEXT,
            task_state TEXT NOT NULL DEFAULT 'idle'
                CHECK(task_state IN (
                    'idle', 'running', 'failed', 'completed', 'cancelled'
                )),
            task_progress INTEGER NOT NULL DEFAULT 0
                CHECK(task_progress BETWEEN 0 AND 100),
            last_error TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(owner_user_id) REFERENCES users(id)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_local_installations_owner
        ON local_installations(owner_user_id)
        """
    )


def ensure_final_user_columns(connection: sqlite3.Connection) -> None:
    """Ensure the five final account columns without altering legacy columns."""
    statements = (
        "ALTER TABLE users ADD COLUMN gender TEXT",
        "ALTER TABLE users ADD COLUMN birth_date TEXT",
        "ALTER TABLE users ADD COLUMN presence TEXT NOT NULL DEFAULT 'offline' "
        "CHECK(presence IN ('online', 'away', 'offline'))",
        "ALTER TABLE users ADD COLUMN last_seen_at TEXT",
        "ALTER TABLE users ADD COLUMN elfie_limit INTEGER DEFAULT NULL "
        "CHECK(elfie_limit IS NULL OR elfie_limit BETWEEN 0 AND 32)",
    )
    for statement in statements:
        _ignore_duplicate_column(connection, statement)


def _ignore_duplicate_column(connection: sqlite3.Connection, statement: str) -> None:
    try:
        connection.execute(statement)
    except sqlite3.OperationalError as error:
        if "duplicate column name" not in str(error).lower():
            raise
