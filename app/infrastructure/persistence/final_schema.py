"""Builder for the final root ``nest.db`` contract."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Final

from app.infrastructure.persistence.sqlite_connection import (
    UnsafeSQLitePathError,
    app_sqlite_connection,
)

FINAL_NEST_DATABASE_NAME: Final = "nest.db"


class FinalNestDatabasePathError(RuntimeError):
    """Raised when the final builder receives a non-final or unsafe path."""

    __slots__ = ("path", "reason")

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"invalid final Nest database path {self.path}: {self.reason}"


def create_final_nest_database(db_path: str | Path) -> Path:
    """Create the final root database at an explicit standard filename."""
    path = Path(db_path)
    if path.name != FINAL_NEST_DATABASE_NAME:
        raise FinalNestDatabasePathError(path, "filename must be nest.db")
    try:
        with app_sqlite_connection(path) as connection:
            initialize_final_schema(connection)
            connection.commit()
    except UnsafeSQLitePathError as error:
        raise FinalNestDatabasePathError(path, error.reason) from error
    return path


def initialize_final_schema(connection: sqlite3.Connection) -> None:
    """Create every final root table, index, and cross-row invariant."""
    for statement in _TABLE_STATEMENTS:
        connection.execute(statement)
    for statement in _INDEX_STATEMENTS:
        connection.execute(statement)
    for statement in _TRIGGER_STATEMENTS:
        connection.execute(statement)


_TABLE_STATEMENTS: Final = (
    """CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        account_id TEXT NOT NULL UNIQUE
            CHECK(account_id=trim(account_id) AND length(account_id) BETWEEN 3 AND 32),
        display_name TEXT
            CHECK(display_name IS NULL OR (display_name=trim(display_name)
                AND length(display_name) BETWEEN 1 AND 64)),
        avatar_color INTEGER NOT NULL DEFAULT 0,
        avatar_kind TEXT NOT NULL DEFAULT 'initials' CHECK(avatar_kind IN ('initials','emoji')),
        avatar_path TEXT CHECK(avatar_path IS NULL OR (length(avatar_path)>0
            AND substr(avatar_path,1,1)<>'/' AND instr(avatar_path,char(92))=0
            AND instr(avatar_path,':')=0
            AND avatar_path<>'..' AND avatar_path NOT LIKE '../%'
            AND avatar_path NOT LIKE '%/../%' AND avatar_path NOT LIKE '%/..')),
        gender TEXT NOT NULL DEFAULT 'male' CHECK(gender IN ('male','female')), birth_date TEXT,
        role TEXT NOT NULL CHECK(role IN ('owner','admin','user')),
        password_hash TEXT NOT NULL CHECK(length(password_hash)>0),
        presence TEXT NOT NULL DEFAULT 'offline' CHECK(presence IN ('online','away','offline')),
        last_seen_at TEXT,
        elfie_limit INTEGER CHECK(elfie_limit IS NULL OR elfie_limit BETWEEN 0 AND 32),
        default_landing_page TEXT NOT NULL DEFAULT 'manage'
            CHECK(default_landing_page IN ('chat','manage')),
        theme_key TEXT NOT NULL DEFAULT 'warm-paper'
            CHECK(theme_key IN ('warm-paper','harbor-blue','orchid-archive','moss-green')),
        language TEXT NOT NULL DEFAULT 'zh-CN' CHECK(language IN ('zh-CN','en-US','ja-JP')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT PRIMARY KEY CHECK(length(token_hash)=64
            AND token_hash NOT GLOB '*[^0-9a-f]*'),
        user_id INTEGER NOT NULL REFERENCES users(id), expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, revoked_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS local_installations (
        installation_id TEXT PRIMARY KEY CHECK(installation_id='local'),
        owner_user_id INTEGER REFERENCES users(id), device_name TEXT, platform TEXT,
        machine_id_hash TEXT CHECK(machine_id_hash IS NULL OR (length(machine_id_hash)=64
            AND machine_id_hash NOT GLOB '*[^0-9a-f]*')),
        setup_state TEXT NOT NULL DEFAULT 'not_started'
            CHECK(setup_state IN ('not_started','in_progress','completed')),
        setup_step TEXT NOT NULL DEFAULT 'not_started'
            CHECK(setup_step IN ('not_started','owner','providers','nest','food')),
        owner_completed_at TEXT, providers_completed_at TEXT, nest_completed_at TEXT,
        food_completed_at TEXT, completed_at TEXT, last_seen_at TEXT,
        active_task_step INTEGER CHECK(active_task_step IS NULL OR active_task_step BETWEEN 1 AND 5),
        active_task_key TEXT,
        task_state TEXT NOT NULL DEFAULT 'idle'
            CHECK(task_state IN ('idle','running','failed','completed','cancelled')),
        task_progress INTEGER NOT NULL DEFAULT 0 CHECK(task_progress BETWEEN 0 AND 100),
        last_error TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS setup_drafts (
        installation_id TEXT PRIMARY KEY CHECK(installation_id='local')
            REFERENCES local_installations(installation_id),
        owner_account_id TEXT
            CHECK(owner_account_id IS NULL OR (owner_account_id=trim(owner_account_id)
                AND length(owner_account_id) BETWEEN 3 AND 32)),
        display_name TEXT
            CHECK(display_name IS NULL OR (display_name=trim(display_name)
                AND length(display_name) BETWEEN 1 AND 64)),
        password_hash TEXT
            CHECK(password_hash IS NULL OR length(password_hash)>0),
        use_local_ollama INTEGER
            CHECK(use_local_ollama IS NULL OR use_local_ollama IN (0,1)),
        model_id TEXT,
        bed_count INTEGER CHECK(bed_count IS NULL OR bed_count BETWEEN 4 AND 32),
        owner_configured INTEGER NOT NULL DEFAULT 0 CHECK(owner_configured IN (0,1)),
        offline_configured INTEGER NOT NULL DEFAULT 0 CHECK(offline_configured IN (0,1)),
        nest_configured INTEGER NOT NULL DEFAULT 0 CHECK(nest_configured IN (0,1)),
        locked_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS nest_settings (
        nest_id TEXT PRIMARY KEY CHECK(nest_id='local'),
        bed_count INTEGER NOT NULL CHECK(bed_count BETWEEN 4 AND 32),
        tick_interval_sec REAL NOT NULL CHECK(tick_interval_sec>0),
        max_elfies INTEGER CHECK(max_elfies IS NULL OR max_elfies>=0),
        applied_world_revision INTEGER CHECK(applied_world_revision IS NULL OR applied_world_revision>=0),
        clock_anchor_seconds REAL NOT NULL DEFAULT 0 CHECK(clock_anchor_seconds>=0),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS elfies (
        elfie_id TEXT PRIMARY KEY CHECK(elfie_id GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'),
        name TEXT NOT NULL CHECK(length(trim(name))>0), owner_user_id INTEGER NOT NULL REFERENCES users(id),
        species TEXT NOT NULL CHECK(length(trim(species))>0), gender TEXT, birth_date TEXT,
        adopted_at TEXT NOT NULL, bed_number INTEGER CHECK(bed_number IS NULL OR bed_number BETWEEN 1 AND 32),
        status TEXT NOT NULL CHECK(status IN ('online','away','offline')), summary TEXT,
        main_food_id TEXT CHECK(main_food_id IS NULL OR length(trim(main_food_id)) > 0),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS food_package_access (
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        food_key TEXT NOT NULL CHECK(length(trim(food_key)) > 0),
        PRIMARY KEY(user_id, food_key)
    )""",
    """CREATE TABLE IF NOT EXISTS external_bodies (
        body_id TEXT PRIMARY KEY, owner_elfie_id TEXT NOT NULL REFERENCES elfies(elfie_id),
        display_name TEXT NOT NULL, body_type TEXT NOT NULL CHECK(length(trim(body_type))>0),
        secret_hash TEXT NOT NULL CHECK(length(secret_hash)=64
            AND secret_hash NOT GLOB '*[^0-9a-f]*'),
        status TEXT NOT NULL CHECK(status IN ('available','active','revoked')),
        last_heartbeat_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, revoked_at TEXT,
        CHECK((status='revoked' AND revoked_at IS NOT NULL)
            OR (status<>'revoked' AND revoked_at IS NULL))
    )""",
    """CREATE TABLE IF NOT EXISTS device_audit_events (
        id INTEGER PRIMARY KEY, body_id TEXT NOT NULL REFERENCES external_bodies(body_id),
        event_type TEXT NOT NULL CHECK(length(trim(event_type))>0),
        detail_json TEXT NOT NULL DEFAULT '{}'
            CHECK(json_valid(detail_json) AND json_type(detail_json)='object'),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS embodiment_sessions (
        elfie_id TEXT PRIMARY KEY REFERENCES elfies(elfie_id),
        body_id TEXT REFERENCES external_bodies(body_id),
        state TEXT NOT NULL CHECK(state IN ('at_nest','switching_to_hosted','hosted','returning_to_nest','offline')),
        lease_expires_at TEXT, lease_version INTEGER NOT NULL CHECK(lease_version>=1),
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CHECK((state IN ('at_nest','offline') AND body_id IS NULL)
            OR (state IN ('switching_to_hosted','hosted','returning_to_nest') AND body_id IS NOT NULL))
    )""",
)

_INDEX_STATEMENTS: Final = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_single_owner ON users(role) WHERE role='owner'",
    "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_local_installations_owner ON local_installations(owner_user_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_elfies_bed_number ON elfies(bed_number) WHERE bed_number IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_food_package_access_food ON food_package_access(food_key)",
    "CREATE INDEX IF NOT EXISTS idx_device_audit_events_body ON device_audit_events(body_id)",
)

_TRIGGER_STATEMENTS: Final = (
    """CREATE TRIGGER IF NOT EXISTS trg_users_total_insert BEFORE INSERT ON users
        WHEN (SELECT COUNT(*) FROM users) >= 16
        BEGIN SELECT RAISE(ABORT,'maximum total account count reached'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_users_admin_insert BEFORE INSERT ON users
        WHEN NEW.role='admin' AND (SELECT COUNT(*) FROM users WHERE role='admin') >= 5
        BEGIN SELECT RAISE(ABORT,'maximum admin account count reached'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_users_admin_update BEFORE UPDATE OF role ON users
        WHEN NEW.role='admin' AND OLD.role<>'admin'
            AND (SELECT COUNT(*) FROM users WHERE role='admin') >= 5
        BEGIN SELECT RAISE(ABORT,'maximum admin account count reached'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_users_owner_delete BEFORE DELETE ON users
        WHEN OLD.role='owner'
        BEGIN SELECT RAISE(ABORT,'Owner account cannot be deleted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_users_owner_demote BEFORE UPDATE OF role ON users
        WHEN OLD.role='owner' AND NEW.role<>'owner'
        BEGIN SELECT RAISE(ABORT,'Owner account cannot be demoted'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_users_owner_grant BEFORE UPDATE OF role ON users
        WHEN OLD.role<>'owner' AND NEW.role='owner'
        BEGIN SELECT RAISE(ABORT,'Owner role cannot be granted by update'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_elfies_bed_insert BEFORE INSERT ON elfies
        WHEN NEW.bed_number IS NOT NULL AND ((SELECT bed_count FROM nest_settings WHERE nest_id='local') IS NULL
        OR NEW.bed_number>(SELECT bed_count FROM nest_settings WHERE nest_id='local'))
        BEGIN SELECT RAISE(ABORT,'bed_number exceeds local Nest bed_count'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_elfies_bed_update BEFORE UPDATE OF bed_number ON elfies
        WHEN NEW.bed_number IS NOT NULL AND ((SELECT bed_count FROM nest_settings WHERE nest_id='local') IS NULL
        OR NEW.bed_number>(SELECT bed_count FROM nest_settings WHERE nest_id='local'))
        BEGIN SELECT RAISE(ABORT,'bed_number exceeds local Nest bed_count'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_nest_bed_count BEFORE UPDATE OF bed_count ON nest_settings
        WHEN EXISTS(SELECT 1 FROM elfies WHERE bed_number>NEW.bed_count)
        BEGIN SELECT RAISE(ABORT,'bed_count is below occupied bed_number'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_lease_body_insert BEFORE INSERT ON embodiment_sessions
        WHEN NEW.body_id IS NOT NULL AND EXISTS(SELECT 1 FROM external_bodies
            WHERE body_id=NEW.body_id AND (status='revoked' OR owner_elfie_id<>NEW.elfie_id))
        BEGIN SELECT RAISE(ABORT,'body is revoked or belongs to another Elfie'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_lease_body_update BEFORE UPDATE OF body_id,elfie_id ON embodiment_sessions
        WHEN NEW.body_id IS NOT NULL AND EXISTS(SELECT 1 FROM external_bodies
            WHERE body_id=NEW.body_id AND (status='revoked' OR owner_elfie_id<>NEW.elfie_id))
        BEGIN SELECT RAISE(ABORT,'body is revoked or belongs to another Elfie'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_lease_version_update BEFORE UPDATE ON embodiment_sessions
        WHEN NEW.lease_version<>OLD.lease_version+1
        BEGIN SELECT RAISE(ABORT,'lease_version must advance exactly once'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_body_owner_update BEFORE UPDATE OF owner_elfie_id ON external_bodies
        WHEN EXISTS(SELECT 1 FROM embodiment_sessions WHERE body_id=NEW.body_id AND elfie_id<>NEW.owner_elfie_id)
        BEGIN SELECT RAISE(ABORT,'body owner must match existing lease'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_body_revoke BEFORE UPDATE OF status,revoked_at ON external_bodies
        WHEN (NEW.status='revoked' OR NEW.revoked_at IS NOT NULL)
            AND EXISTS(SELECT 1 FROM embodiment_sessions WHERE body_id=NEW.body_id)
        BEGIN SELECT RAISE(ABORT,'body must be released before revoke'); END""",
)
