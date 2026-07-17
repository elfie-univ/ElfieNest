"""SQLite schema creation and migrations for the ElfieNest data store."""

from __future__ import annotations

import sqlite3
from typing import Final

CURRENT_SCHEMA_VERSION: Final[int] = 5


class OwnerSchemaMigrationError(RuntimeError):
    """数据库包含不支持的 Owner 角色状态，必须人工确认后迁移。"""


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Create all tables and apply every known migration."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('owner', 'user')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            nickname TEXT DEFAULT NULL,
            avatar_color INTEGER DEFAULT 0,
            avatar_kind TEXT DEFAULT 'initials'
        )
        """
    )

    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version < 5:
        _validate_owner_roles(connection)

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    _ensure_nest_tables(connection)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS elfie_registry (
            id INTEGER PRIMARY KEY,
            elfie_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            owner_user_id INTEGER,
            anatomy_type TEXT DEFAULT 'biped',
            config_dir TEXT,
            personality_style TEXT,
            height TEXT DEFAULT 'standard',
            build TEXT DEFAULT 'standard',
            bed_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(owner_user_id) REFERENCES users(id),
            FOREIGN KEY(bed_id) REFERENCES beds(id)
        )
        """
    )

    if version < 1:
        connection.execute("PRAGMA user_version = 1")
    if version < 2:
        _migrate_v1_to_v2(connection)
    if version < 3:
        _migrate_v2_to_v3(connection)
    if version < 4:
        _migrate_v3_to_v4(connection)
    if version < 5:
        _migrate_v4_to_v5(connection)
    _ensure_owner_index(connection)


def migrate_schema(connection: sqlite3.Connection) -> None:
    """Apply pending migrations to an already opened database connection."""
    try:
        initialize_schema(connection)
        connection.commit()
    except (OwnerSchemaMigrationError, sqlite3.Error):
        connection.rollback()
        raise


def _migrate_v1_to_v2(connection: sqlite3.Connection) -> None:
    for statement in (
        "ALTER TABLE users ADD COLUMN nickname TEXT DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN avatar_color INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN avatar_kind TEXT DEFAULT 'initials'",
    ):
        _ignore_duplicate_column(connection, statement)
    connection.execute("PRAGMA user_version = 2")


def _ensure_nest_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            max_capacity INTEGER NOT NULL DEFAULT 4,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS beds (
            id INTEGER PRIMARY KEY,
            room_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            grid_x INTEGER DEFAULT 0,
            grid_y INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(room_id) REFERENCES rooms(id)
        )
        """
    )


def _ensure_chat_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY,
            elfie_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            sender TEXT NOT NULL CHECK(sender IN ('user', 'elfie', 'system')),
            text TEXT NOT NULL,
            meta TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(elfie_id) REFERENCES elfie_registry(elfie_id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_chat_messages_lookup
        ON chat_messages(elfie_id, user_id, created_at)
        """
    )


def _migrate_v2_to_v3(connection: sqlite3.Connection) -> None:
    _ensure_nest_tables(connection)
    _ignore_duplicate_column(
        connection, "ALTER TABLE elfie_registry ADD COLUMN bed_id INTEGER"
    )
    connection.execute("PRAGMA user_version = 3")


def _migrate_v3_to_v4(connection: sqlite3.Connection) -> None:
    _ensure_chat_tables(connection)
    connection.execute("PRAGMA user_version = 4")


def _migrate_v4_to_v5(connection: sqlite3.Connection) -> None:
    columns = _table_columns(connection, "users")
    _validate_owner_roles(connection)
    sql = str(
        connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'users'"
        ).fetchone()[0]
    )
    has_owner_role = "'owner'" in sql or '"owner"' in sql
    if "updated_at" not in columns or not has_owner_role:
        _rebuild_users_table(connection, columns)
    connection.execute(
        "UPDATE users SET updated_at = created_at WHERE updated_at IS NULL"
    )
    _ensure_owner_index(connection)
    connection.execute("PRAGMA user_version = 5")


def _validate_owner_roles(connection: sqlite3.Connection) -> None:
    """在任何 schema 写入前拒绝未知角色或多个 Owner。"""
    invalid_roles = tuple(
        str(row[0])
        for row in connection.execute(
            "SELECT DISTINCT role FROM users "
            "WHERE role IS NULL OR role NOT IN ('owner', 'user')"
        ).fetchall()
    )
    if invalid_roles:
        raise OwnerSchemaMigrationError(
            "发现不支持的用户角色: " + ", ".join(invalid_roles)
        )
    owner_count = int(
        connection.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'owner'"
        ).fetchone()[0]
    )
    if owner_count > 1:
        raise OwnerSchemaMigrationError(
            f"数据库包含 {owner_count} 个 Owner；请先人工确认保留的 Owner"
        )


def _rebuild_users_table(
    connection: sqlite3.Connection, existing_columns: set[str]
) -> None:
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute("DROP TABLE IF EXISTS users_new")
    connection.execute(
        """
        CREATE TABLE users_new (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('owner', 'user')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            nickname TEXT DEFAULT NULL,
            avatar_color INTEGER DEFAULT 0,
            avatar_kind TEXT DEFAULT 'initials'
        )
        """
    )
    columns = ("id", "username", "password_hash", "role", "created_at")
    optional = ("nickname", "avatar_color", "avatar_kind")
    target = list(columns) + ["updated_at"] + list(optional)
    source = []
    for column in target:
        if column in existing_columns:
            source.append(column)
        elif column == "updated_at":
            source.append("created_at" if "created_at" in existing_columns else "CURRENT_TIMESTAMP")
        else:
            source.append(_default_expression(column))
    connection.execute(
        "INSERT INTO users_new (" + ", ".join(target) + ") SELECT "
        + ", ".join(source)
        + " FROM users"
    )
    connection.execute("DROP TABLE users")
    connection.execute("ALTER TABLE users_new RENAME TO users")
    connection.execute("PRAGMA foreign_keys = ON")


def _default_expression(column: str) -> str:
    if column == "created_at":
        return "CURRENT_TIMESTAMP"
    if column == "updated_at":
        return "created_at"
    if column == "avatar_color":
        return "0"
    if column == "avatar_kind":
        return "'initials'"
    return "NULL"


def _ensure_owner_index(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_single_owner "
        "ON users(role) WHERE role = 'owner'"
    )


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table_name})")}


def _ignore_duplicate_column(connection: sqlite3.Connection, statement: str) -> None:
    try:
        connection.execute(statement)
    except sqlite3.OperationalError as error:
        if "duplicate column name" not in str(error).lower():
            raise
