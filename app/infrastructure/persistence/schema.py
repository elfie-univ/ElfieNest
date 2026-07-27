"""SQLite schema creation and migrations for the ElfieNest data store."""

from __future__ import annotations

import sqlite3
from typing import Final

from app.infrastructure.persistence.nest_schema import (
    NestSchemaMigrationError,
    ensure_legacy_nest_tables,
    ensure_nest_semantic_tables,
    migrate_legacy_nest_layout_to_semantic_tables,
)

CURRENT_SCHEMA_VERSION: Final[int] = 15


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
            avatar_kind TEXT DEFAULT 'initials',
            avatar_path TEXT DEFAULT NULL,
            default_landing_page TEXT NOT NULL DEFAULT 'manage'
            CHECK(default_landing_page IN ('chat', 'manage')),
            theme_key TEXT NOT NULL DEFAULT 'warm-paper'
            CHECK(theme_key IN ('warm-paper', 'harbor-blue', 'orchid-archive', 'moss-green')),
            elfie_quota_override INTEGER DEFAULT NULL
            CHECK(elfie_quota_override IS NULL OR elfie_quota_override BETWEEN 1 AND 32)
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
    ensure_legacy_nest_tables(connection)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS elfie_registry (
            id INTEGER PRIMARY KEY,
            elfie_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            owner_user_id INTEGER,
            anatomy_type TEXT DEFAULT 'biped',
            species_id TEXT NOT NULL DEFAULT 'fox',
            profile_schema_version INTEGER NOT NULL DEFAULT 1,
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
    if version < 6:
        _migrate_v5_to_v6(connection)
    if not _table_exists(connection, "nest_config"):
        migrate_legacy_nest_layout_to_semantic_tables(connection)
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    else:
        ensure_nest_semantic_tables(connection)

    _ensure_default_landing_page_column(connection)
    _ensure_theme_key_column(connection)
    if version < 8:
        _migrate_v7_to_v8(connection)
    if version < 9:
        _migrate_v8_to_v9(connection)
    if version < 10:
        _migrate_v9_to_v10(connection)
    if version < 11:
        _migrate_v10_to_v11(connection)
    if version < 12:
        _migrate_v11_to_v12(connection)
    if version < 13:
        _migrate_v12_to_v13(connection)
    if version < 14:
        _migrate_v13_to_v14(connection)
    if version < 15:
        _migrate_v14_to_v15(connection)
    _ensure_owner_index(connection)


def migrate_schema(connection: sqlite3.Connection) -> None:
    """Apply pending migrations to an already opened database connection."""
    try:
        initialize_schema(connection)
        connection.commit()
    except (OwnerSchemaMigrationError, NestSchemaMigrationError, sqlite3.Error):
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


def _migrate_v2_to_v3(connection: sqlite3.Connection) -> None:
    ensure_legacy_nest_tables(connection)
    _ignore_duplicate_column(
        connection, "ALTER TABLE elfie_registry ADD COLUMN bed_id INTEGER"
    )
    connection.execute("PRAGMA user_version = 3")


def _migrate_v3_to_v4(connection: sqlite3.Connection) -> None:
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


def _migrate_v5_to_v6(connection: sqlite3.Connection) -> None:
    """增加稳定物种和档案版本；旧 anatomy_type 仅保留兼容读取。"""
    _ignore_duplicate_column(
        connection,
        "ALTER TABLE elfie_registry ADD COLUMN species_id TEXT NOT NULL DEFAULT 'fox'",
    )
    _ignore_duplicate_column(
        connection,
        "ALTER TABLE elfie_registry "
        "ADD COLUMN profile_schema_version INTEGER NOT NULL DEFAULT 1",
    )
    connection.execute("PRAGMA user_version = 6")


def _ensure_default_landing_page_column(connection: sqlite3.Connection) -> None:
    """Keep the APP landing preference available across historical v7 layouts."""
    _ignore_duplicate_column(
        connection,
        "ALTER TABLE users ADD COLUMN default_landing_page "
        "TEXT NOT NULL DEFAULT 'manage' CHECK(default_landing_page IN ('chat', 'manage'))",
    )


def _ensure_theme_key_column(connection: sqlite3.Connection) -> None:
    """Keep the user-selected Web theme available across historical layouts."""
    _ignore_duplicate_column(
        connection,
        "ALTER TABLE users ADD COLUMN theme_key TEXT NOT NULL DEFAULT 'warm-paper' "
        "CHECK(theme_key IN ('warm-paper', 'harbor-blue', 'orchid-archive', 'moss-green'))",
    )


def _migrate_v7_to_v8(connection: sqlite3.Connection) -> None:
    """Add persistent embodiment session/lease facts without altering old rows."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS embodiment_sessions (
            elfie_id TEXT PRIMARY KEY,
            session_id TEXT,
            state TEXT NOT NULL CHECK(state IN (
                'at_nest', 'switching_to_hosted', 'hosted',
                'returning_to_nest', 'offline'
            )),
            body_id TEXT,
            lease_expires_at REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(elfie_id) REFERENCES elfie_registry(elfie_id)
        )
        """
    )
    connection.execute("PRAGMA user_version = 8")


def _migrate_v8_to_v9(connection: sqlite3.Connection) -> None:
    """Add local-device credential facts without storing raw device secrets."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS devices (
            device_id TEXT PRIMARY KEY,
            owner_user_id INTEGER NOT NULL,
            display_name TEXT NOT NULL,
            secret_hash TEXT NOT NULL,
            revoked_at TIMESTAMP,
            last_heartbeat_at REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(owner_user_id) REFERENCES users(id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS device_audit_events (
            id INTEGER PRIMARY KEY,
            device_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(device_id) REFERENCES devices(device_id)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_devices_owner ON devices(owner_user_id)"
    )
    connection.execute("PRAGMA user_version = 9")


def _migrate_v9_to_v10(connection: sqlite3.Connection) -> None:
    """Delete the unreleased Nest-level chat store.

    Chat history belongs only to each elfie's workspace.  This development-only
    migration deliberately discards the obsolete table instead of copying it.
    """
    connection.execute("DROP TABLE IF EXISTS chat_messages")
    connection.execute("PRAGMA user_version = 10")


def _migrate_v10_to_v11(connection: sqlite3.Connection) -> None:
    """Persist one validated visual theme preference per user."""
    _ensure_theme_key_column(connection)
    connection.execute("PRAGMA user_version = 11")


def _migrate_v11_to_v12(connection: sqlite3.Connection) -> None:
    """Replace generated avatar fields with a private local image reference."""
    _ignore_duplicate_column(
        connection, "ALTER TABLE users ADD COLUMN avatar_path TEXT DEFAULT NULL"
    )
    connection.execute("PRAGMA user_version = 12")


def _migrate_v12_to_v13(connection: sqlite3.Connection) -> None:
    """Allow one nullable per-user adoption-limit override."""
    _ignore_duplicate_column(
        connection,
        "ALTER TABLE users ADD COLUMN elfie_quota_override INTEGER DEFAULT NULL "
        "CHECK(elfie_quota_override IS NULL OR elfie_quota_override BETWEEN 1 AND 32)",
    )
    connection.execute("PRAGMA user_version = 13")


def _migrate_v13_to_v14(connection: sqlite3.Connection) -> None:
    """Persist resumable first-run setup state without storing credentials."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS setup_progress (
            singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
            progress_schema_version INTEGER NOT NULL DEFAULT 1,
            current_step INTEGER NOT NULL DEFAULT 1 CHECK(current_step BETWEEN 1 AND 5),
            owner_user_id INTEGER,
            owner_completed_at TIMESTAMP,
            ollama_decision TEXT CHECK(ollama_decision IN (
                'bound_existing', 'install_official', 'skipped'
            )),
            ollama_endpoint TEXT,
            nest_completed_at TIMESTAMP,
            model_decision TEXT CHECK(model_decision IN ('configured', 'skipped')),
            model_reference TEXT,
            active_task_step INTEGER CHECK(active_task_step BETWEEN 1 AND 5),
            active_task_key TEXT,
            task_state TEXT NOT NULL DEFAULT 'idle' CHECK(task_state IN (
                'idle', 'running', 'failed', 'completed', 'cancelled'
            )),
            task_progress INTEGER NOT NULL DEFAULT 0 CHECK(task_progress BETWEEN 0 AND 100),
            last_error TEXT,
            completed_at TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(owner_user_id) REFERENCES users(id)
        )
        """
    )
    connection.execute("INSERT OR IGNORE INTO setup_progress (singleton_id) VALUES (1)")
    owner = connection.execute(
        "SELECT id FROM users WHERE role = 'owner' ORDER BY id LIMIT 1"
    ).fetchone()
    if owner is not None:
        connection.execute(
            """
            UPDATE setup_progress
            SET owner_user_id = ?,
                owner_completed_at = COALESCE(owner_completed_at, CURRENT_TIMESTAMP),
                current_step = CASE WHEN current_step = 1 THEN 2 ELSE current_step END,
                updated_at = CURRENT_TIMESTAMP
            WHERE singleton_id = 1
            """,
            (int(owner[0]),),
        )
    connection.execute("PRAGMA user_version = 14")


def _migrate_v14_to_v15(connection: sqlite3.Connection) -> None:
    """Raise the semantic Nest minimum to four without dropping Nest relations."""
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'nest_config'"
    ).fetchone()
    if row is None:
        ensure_nest_semantic_tables(connection)
    elif "BETWEEN 4 AND 32" not in str(row[0]):
        connection.execute("PRAGMA foreign_keys = OFF")
        try:
            connection.execute(
                "UPDATE nest_config SET desired_bed_count = 4 WHERE desired_bed_count < 4"
            )
            connection.execute(
                """
                CREATE TABLE nest_config_v15 (
                    nest_id TEXT PRIMARY KEY,
                    desired_bed_count INTEGER NOT NULL
                        CHECK(desired_bed_count BETWEEN 4 AND 32),
                    applied_world_revision INTEGER,
                    clock_anchor_seconds REAL NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                INSERT INTO nest_config_v15
                    (nest_id, desired_bed_count, applied_world_revision,
                     clock_anchor_seconds, created_at)
                SELECT nest_id, desired_bed_count, applied_world_revision,
                       clock_anchor_seconds, created_at
                FROM nest_config
                """
            )
            connection.execute("DROP TABLE nest_config")
            connection.execute("ALTER TABLE nest_config_v15 RENAME TO nest_config")
        finally:
            connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA user_version = 15")


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
            source.append(
                "created_at"
                if "created_at" in existing_columns
                else "CURRENT_TIMESTAMP"
            )
        else:
            source.append(_default_expression(column))
    connection.execute(
        "INSERT INTO users_new ("
        + ", ".join(target)
        + ") SELECT "
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
    return {
        str(row[1]) for row in connection.execute(f"PRAGMA table_info({table_name})")
    }


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    """Return whether a SQLite table exists in the current schema."""
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _ignore_duplicate_column(connection: sqlite3.Connection, statement: str) -> None:
    try:
        connection.execute(statement)
    except sqlite3.OperationalError as error:
        if "duplicate column name" not in str(error).lower():
            raise
