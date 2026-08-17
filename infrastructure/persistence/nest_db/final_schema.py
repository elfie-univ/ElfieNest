"""Root Infrastructure builder for the final ``nest.db`` contract."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Final

from infrastructure.persistence.nest_db.sqlite_connection import (
    UnsafeSQLitePathError,
    app_sqlite_connection,
)

FINAL_NEST_DATABASE_NAME: Final = "nest.db"

# Keep the inspection contract next to the schema builder so a database with
# the current table names but an older column set cannot be mistaken for READY.
FINAL_TABLE_COLUMNS: Final[dict[str, frozenset[str]]] = {
    "users": frozenset(
        {
            "id",
            "account_id",
            "display_name",
            "avatar_color",
            "avatar_kind",
            "avatar_path",
            "gender",
            "birth_date",
            "role",
            "password_hash",
            "presence",
            "last_seen_at",
            "elfie_limit",
            "default_landing_page",
            "theme_key",
            "language",
            "created_at",
            "updated_at",
        }
    ),
    "sessions": frozenset(
        {"token_hash", "user_id", "expires_at", "created_at", "revoked_at"}
    ),
    "local_installations": frozenset(
        {
            "installation_id",
            "owner_user_id",
            "device_name",
            "platform",
            "machine_id_hash",
            "status",
            "install_step",
            "install_action",
            "task_status",
            "task_progress",
            "last_error",
            "setup_draft_json",
            "setup_completed_at",
            "created_at",
            "updated_at",
        }
    ),
    "nest_settings": frozenset(
        {
            "nest_id",
            "bed_count",
            "tick_interval_sec",
            "max_elfies",
            "applied_world_revision",
            "world_catalog_json",
            "clock_anchor_seconds",
            "clock_paused",
            "time_scale",
            "environment_desired_json",
            "environment_rules_json",
            "created_at",
            "updated_at",
        }
    ),
    "elfies": frozenset(
        {
            "elfie_id",
            "name",
            "original_name",
            "owner_user_id",
            "species",
            "gender",
            "birth_date",
            "adopted_at",
            "home_anchor_id",
            "status",
            "summary",
            "main_food_id",
            "created_at",
            "updated_at",
        }
    ),
    "food_packages": frozenset(
        {
            "food_key",
            "display_name",
            "system_role",
            "primary_model_ref",
            "reasoning_model_ref",
            "vision_model_ref",
            "tool_model_ref",
            "fallback_model_ref",
            "required_roles_json",
            "visibility_mode",
            "visible_user_ids_json",
            "enabled",
            "archived",
            "created_at",
            "updated_at",
        }
    ),
    "external_bodies": frozenset(
        {
            "body_id",
            "owner_elfie_id",
            "display_name",
            "body_type",
            "secret_hash",
            "status",
            "last_heartbeat_at",
            "created_at",
            "updated_at",
            "revoked_at",
        }
    ),
    "device_audit_events": frozenset(
        {"id", "body_id", "event_type", "detail_json", "created_at"}
    ),
    "embodiment_sessions": frozenset(
        {
            "elfie_id",
            "body_id",
            "state",
            "lease_expires_at",
            "lease_version",
            "updated_at",
        }
    ),
}

# Only column additions that SQLite can apply in place without rebuilding a
# table are admitted here. A new required column without a constant default,
# a key, or a uniqueness constraint remains an explicit incompatibility.
_ADDITIVE_COLUMN_DEFINITIONS: Final[dict[str, str]] = {
    "users.display_name": (
        "TEXT CHECK(display_name IS NULL OR (display_name=trim(display_name) "
        "AND length(display_name) BETWEEN 1 AND 64))"
    ),
    "users.avatar_color": "INTEGER NOT NULL DEFAULT 0",
    "users.avatar_kind": (
        "TEXT NOT NULL DEFAULT 'initials' CHECK(avatar_kind IN ('initials','emoji'))"
    ),
    "users.avatar_path": (
        "TEXT CHECK(avatar_path IS NULL OR (length(avatar_path)>0 "
        "AND substr(avatar_path,1,1)<>'/' AND instr(avatar_path,char(92))=0 "
        "AND instr(avatar_path,':')=0 AND avatar_path<>'..' "
        "AND avatar_path NOT LIKE '../%' AND avatar_path NOT LIKE '%/../%' "
        "AND avatar_path NOT LIKE '%/..'))"
    ),
    "users.gender": "TEXT NOT NULL DEFAULT 'male' CHECK(gender IN ('male','female'))",
    "users.birth_date": "TEXT",
    "users.presence": (
        "TEXT NOT NULL DEFAULT 'offline' CHECK(presence IN ('online','away','offline'))"
    ),
    "users.last_seen_at": "TEXT",
    "users.elfie_limit": (
        "INTEGER CHECK(elfie_limit IS NULL OR elfie_limit BETWEEN 0 AND 32)"
    ),
    "users.default_landing_page": (
        "TEXT NOT NULL DEFAULT 'manage' CHECK(default_landing_page IN ('chat','manage'))"
    ),
    "users.theme_key": (
        "TEXT NOT NULL DEFAULT 'warm-paper' "
        "CHECK(theme_key IN ('warm-paper','harbor-blue','orchid-archive','moss-green'))"
    ),
    "users.language": (
        "TEXT NOT NULL DEFAULT 'zh-CN' CHECK(language IN ('zh-CN','en-US','ja-JP'))"
    ),
    "sessions.revoked_at": "TEXT",
    "local_installations.owner_user_id": "INTEGER REFERENCES users(id)",
    "local_installations.device_name": "TEXT",
    "local_installations.platform": "TEXT",
    "local_installations.machine_id_hash": (
        "TEXT CHECK(machine_id_hash IS NULL OR (length(machine_id_hash)=64 "
        "AND machine_id_hash NOT GLOB '*[^0-9a-f]*'))"
    ),
    "local_installations.status": (
        "TEXT NOT NULL DEFAULT 'not_started' "
        "CHECK(status IN ('not_started','in_progress','completed'))"
    ),
    "local_installations.install_step": (
        "INTEGER CHECK(install_step IS NULL OR install_step BETWEEN 1 AND 5)"
    ),
    "local_installations.install_action": "TEXT",
    "local_installations.task_status": (
        "TEXT NOT NULL DEFAULT 'idle' "
        "CHECK(task_status IN ('idle','running','failed','completed','cancelled'))"
    ),
    "local_installations.task_progress": (
        "INTEGER NOT NULL DEFAULT 0 CHECK(task_progress BETWEEN 0 AND 100)"
    ),
    "local_installations.last_error": "TEXT",
    "local_installations.setup_draft_json": (
        "TEXT CHECK(setup_draft_json IS NULL OR "
        "(json_valid(setup_draft_json) AND json_type(setup_draft_json) = 'object'))"
    ),
    "local_installations.setup_completed_at": "TEXT",
    "nest_settings.max_elfies": "INTEGER CHECK(max_elfies IS NULL OR max_elfies>=0)",
    "nest_settings.applied_world_revision": (
        "INTEGER CHECK(applied_world_revision IS NULL OR applied_world_revision>=0)"
    ),
    "nest_settings.world_catalog_json": (
        "TEXT CHECK(world_catalog_json IS NULL OR "
        "(json_valid(world_catalog_json) AND json_type(world_catalog_json)='object'))"
    ),
    "nest_settings.clock_anchor_seconds": (
        "REAL NOT NULL DEFAULT 0 CHECK(clock_anchor_seconds>=0)"
    ),
    "nest_settings.clock_paused": "INTEGER NOT NULL DEFAULT 0 CHECK(clock_paused IN (0,1))",
    "nest_settings.time_scale": "REAL NOT NULL DEFAULT 1 CHECK(time_scale>0)",
    "nest_settings.environment_desired_json": (
        'TEXT NOT NULL DEFAULT \'{"object_id":"nest/environment","lights_on":true,"quiet_mode":false}\' '
        "CHECK(json_valid(environment_desired_json) AND json_type(environment_desired_json)='object')"
    ),
    "nest_settings.environment_rules_json": (
        "TEXT NOT NULL DEFAULT '[]' "
        "CHECK(json_valid(environment_rules_json) AND json_type(environment_rules_json)='array')"
    ),
    "elfies.original_name": (
        "TEXT NOT NULL DEFAULT '' CHECK(length(trim(original_name))>=0)"
    ),
    "elfies.gender": "TEXT",
    "elfies.birth_date": "TEXT",
    "elfies.home_anchor_id": (
        "TEXT CHECK(home_anchor_id IS NULL OR "
        "(home_anchor_id=trim(home_anchor_id) AND length(home_anchor_id)>0))"
    ),
    "elfies.summary": "TEXT",
    "elfies.main_food_id": (
        "TEXT CHECK(main_food_id IS NULL OR length(trim(main_food_id)) > 0)"
    ),
    "food_packages.system_role": (
        "TEXT CHECK(system_role IS NULL OR system_role IN ('common','emergency'))"
    ),
    "food_packages.primary_model_ref": "TEXT",
    "food_packages.reasoning_model_ref": "TEXT",
    "food_packages.vision_model_ref": "TEXT",
    "food_packages.tool_model_ref": "TEXT",
    "food_packages.fallback_model_ref": "TEXT",
    "food_packages.required_roles_json": (
        "TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(required_roles_json) "
        "AND json_type(required_roles_json)='array')"
    ),
    "food_packages.visible_user_ids_json": "TEXT NOT NULL DEFAULT '[]'",
    "food_packages.enabled": "INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1))",
    "food_packages.archived": "INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1))",
    "external_bodies.last_heartbeat_at": "TEXT",
    "external_bodies.revoked_at": "TEXT",
    "device_audit_events.detail_json": (
        "TEXT NOT NULL DEFAULT '{}' "
        "CHECK(json_valid(detail_json) AND json_type(detail_json)='object')"
    ),
    "embodiment_sessions.body_id": "TEXT REFERENCES external_bodies(body_id)",
    "embodiment_sessions.lease_expires_at": "TEXT",
}


class FinalNestDatabasePathError(RuntimeError):
    """Raised when the final builder receives a non-final or unsafe path."""

    __slots__ = ("path", "reason")

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"invalid final Nest database path {self.path}: {self.reason}"


class FinalNestSchemaRepairError(RuntimeError):
    """Raised when a missing column is outside the narrow additive contract."""

    __slots__ = ("missing_columns",)

    def __init__(self, missing_columns: tuple[str, ...]) -> None:
        self.missing_columns = missing_columns
        super().__init__(str(self))

    def __str__(self) -> str:
        return "数据库结构与当前版本不兼容：缺少不可安全补齐的字段 " + ", ".join(
            self.missing_columns
        )


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
    _initialize_final_tables(connection)
    _initialize_final_objects(connection)


def repair_final_nest_database(db_path: str | Path) -> Path:
    """Apply only safe additive fixes to an existing current root database."""
    path = Path(db_path)
    if path.name != FINAL_NEST_DATABASE_NAME:
        raise FinalNestDatabasePathError(path, "filename must be nest.db")
    try:
        with app_sqlite_connection(path) as connection:
            # Tables must exist before missing columns can be classified. Do
            # not create indexes or triggers until those columns are present.
            _initialize_final_tables(connection)
            add_missing_final_schema_columns(connection)
            _initialize_final_objects(connection)
            connection.commit()
    except UnsafeSQLitePathError as error:
        raise FinalNestDatabasePathError(path, error.reason) from error
    return path


def add_missing_final_schema_columns(connection: sqlite3.Connection) -> tuple[str, ...]:
    """Add only allow-listed nullable/default current-contract columns."""
    missing = missing_final_schema_columns(connection)
    unsupported = unsupported_final_schema_columns(missing)
    if unsupported:
        raise FinalNestSchemaRepairError(unsupported)
    for qualified_name in missing:
        table_name, column_name = qualified_name.split(".", 1)
        connection.execute(
            f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" '
            f"{_ADDITIVE_COLUMN_DEFINITIONS[qualified_name]}"
        )
    return missing


def unsupported_final_schema_columns(
    missing_columns: tuple[str, ...],
) -> tuple[str, ...]:
    """Return missing columns that cannot be added by the narrow repair."""
    return tuple(
        column_name
        for column_name in missing_columns
        if column_name not in _ADDITIVE_COLUMN_DEFINITIONS
    )


def _initialize_final_tables(connection: sqlite3.Connection) -> None:
    for statement in _TABLE_STATEMENTS:
        connection.execute(statement)


def _initialize_final_objects(connection: sqlite3.Connection) -> None:
    for statement in _INDEX_STATEMENTS:
        connection.execute(statement)
    for statement in _TRIGGER_STATEMENTS:
        connection.execute(statement)
    for statement in _SEED_STATEMENTS:
        connection.execute(statement)


def missing_final_schema_columns(connection: sqlite3.Connection) -> tuple[str, ...]:
    """Return final-contract columns absent from an existing SQLite database."""
    missing: list[str] = []
    for table_name, expected_columns in FINAL_TABLE_COLUMNS.items():
        actual_columns = {
            str(row[1])
            for row in connection.execute(f"PRAGMA table_info({table_name})")
        }
        missing.extend(
            f"{table_name}.{column_name}"
            for column_name in sorted(expected_columns - actual_columns)
        )
    return tuple(missing)


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
        status TEXT NOT NULL DEFAULT 'not_started'
            CHECK(status IN ('not_started','in_progress','completed')),
        install_step INTEGER CHECK(install_step IS NULL OR install_step BETWEEN 1 AND 5),
        install_action TEXT,
        task_status TEXT NOT NULL DEFAULT 'idle'
            CHECK(task_status IN ('idle','running','failed','completed','cancelled')),
        task_progress INTEGER NOT NULL DEFAULT 0 CHECK(task_progress BETWEEN 0 AND 100),
        last_error TEXT,
        setup_draft_json TEXT CHECK(
            setup_draft_json IS NULL OR
            (json_valid(setup_draft_json) AND json_type(setup_draft_json) = 'object')
        ),
        setup_completed_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS nest_settings (
        nest_id TEXT PRIMARY KEY CHECK(nest_id='local-nest'),
        bed_count INTEGER NOT NULL CHECK(bed_count BETWEEN 4 AND 32),
        tick_interval_sec REAL NOT NULL CHECK(tick_interval_sec>0),
        max_elfies INTEGER CHECK(max_elfies IS NULL OR max_elfies>=0),
        applied_world_revision INTEGER CHECK(applied_world_revision IS NULL OR applied_world_revision>=0),
        world_catalog_json TEXT CHECK(
            world_catalog_json IS NULL OR
            (json_valid(world_catalog_json) AND json_type(world_catalog_json)='object')
        ),
        clock_anchor_seconds REAL NOT NULL DEFAULT 0 CHECK(clock_anchor_seconds>=0),
        clock_paused INTEGER NOT NULL DEFAULT 0 CHECK(clock_paused IN (0,1)),
        time_scale REAL NOT NULL DEFAULT 1 CHECK(time_scale>0),
        environment_desired_json TEXT NOT NULL DEFAULT '{"object_id":"nest/environment","lights_on":true,"quiet_mode":false}'
            CHECK(json_valid(environment_desired_json) AND json_type(environment_desired_json)='object'),
        environment_rules_json TEXT NOT NULL DEFAULT '[]'
            CHECK(json_valid(environment_rules_json) AND json_type(environment_rules_json)='array'),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS elfies (
        elfie_id TEXT PRIMARY KEY CHECK(elfie_id GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'),
        name TEXT NOT NULL CHECK(length(trim(name))>0),
        original_name TEXT NOT NULL DEFAULT '' CHECK(length(trim(original_name))>=0),
        owner_user_id INTEGER NOT NULL REFERENCES users(id),
        species TEXT NOT NULL CHECK(length(trim(species))>0), gender TEXT, birth_date TEXT,
        adopted_at TEXT NOT NULL,
        home_anchor_id TEXT CHECK(
            home_anchor_id IS NULL OR
            (home_anchor_id=trim(home_anchor_id) AND length(home_anchor_id)>0)
        ),
        status TEXT NOT NULL CHECK(status IN ('online','away','offline')), summary TEXT,
        main_food_id TEXT CHECK(main_food_id IS NULL OR length(trim(main_food_id)) > 0),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS food_packages (
        food_key TEXT PRIMARY KEY
            CHECK(food_key=trim(food_key) AND length(food_key) BETWEEN 1 AND 128),
        display_name TEXT NOT NULL
            CHECK(display_name=trim(display_name) AND length(display_name) BETWEEN 1 AND 128),
        system_role TEXT
            CHECK(system_role IS NULL OR system_role IN ('common','emergency')),
        primary_model_ref TEXT,
        reasoning_model_ref TEXT,
        vision_model_ref TEXT,
        tool_model_ref TEXT,
        fallback_model_ref TEXT,
        required_roles_json TEXT NOT NULL DEFAULT '[]' CHECK(
            json_valid(required_roles_json)
            AND json_type(required_roles_json)='array'
        ),
        visibility_mode TEXT NOT NULL CHECK(visibility_mode IN ('global','users')),
        visible_user_ids_json TEXT NOT NULL DEFAULT '[]',
        enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
        archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CHECK(
            CASE
                WHEN json_valid(visible_user_ids_json)=0 THEN 0
                WHEN json_type(visible_user_ids_json)<>'array' THEN 0
                WHEN visibility_mode='global' THEN json_array_length(visible_user_ids_json)=0
                WHEN visibility_mode='users' THEN json_array_length(visible_user_ids_json)>0
                ELSE 0
            END
        ),
        CHECK(archived=0 OR enabled=0),
        CHECK(enabled=0 OR (primary_model_ref IS NOT NULL AND length(trim(primary_model_ref))>0)),
        CHECK(system_role IS NULL OR (visibility_mode='global' AND archived=0)),
        CHECK(
            system_role IS NULL
            OR (system_role='common' AND food_key='food_common')
            OR (system_role='emergency' AND food_key='food_emergency')
        )
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
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_elfies_home_anchor_id ON elfies(home_anchor_id) WHERE home_anchor_id IS NOT NULL",
    """CREATE UNIQUE INDEX IF NOT EXISTS idx_food_packages_common_role
        ON food_packages(system_role) WHERE system_role='common'""",
    """CREATE UNIQUE INDEX IF NOT EXISTS idx_food_packages_emergency_role
        ON food_packages(system_role) WHERE system_role='emergency'""",
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
    """CREATE TRIGGER IF NOT EXISTS trg_nest_bed_count BEFORE UPDATE OF bed_count ON nest_settings
        WHEN (SELECT COUNT(*) FROM elfies)>NEW.bed_count
        BEGIN SELECT RAISE(ABORT,'bed_count is below current resident capacity'); END""",
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
    """CREATE TRIGGER IF NOT EXISTS trg_food_packages_updated_at
        AFTER UPDATE ON food_packages
        WHEN NEW.updated_at=OLD.updated_at
        BEGIN
            UPDATE food_packages SET updated_at=CURRENT_TIMESTAMP WHERE food_key=NEW.food_key;
        END""",
    """CREATE TRIGGER IF NOT EXISTS trg_food_packages_user_ids_insert
        BEFORE INSERT ON food_packages
        WHEN json_valid(NEW.visible_user_ids_json)=1
            AND (
                EXISTS(
                    SELECT 1 FROM json_each(NEW.visible_user_ids_json)
                    WHERE type<>'integer' OR CAST(value AS INTEGER)<=0
                )
                OR EXISTS(
                    SELECT value FROM json_each(NEW.visible_user_ids_json)
                    GROUP BY value HAVING COUNT(*)>1
                )
            )
        BEGIN SELECT RAISE(ABORT,'visible_user_ids_json must contain unique positive integers'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_food_packages_user_ids_update
        BEFORE UPDATE OF visible_user_ids_json ON food_packages
        WHEN json_valid(NEW.visible_user_ids_json)=1
            AND (
                EXISTS(
                    SELECT 1 FROM json_each(NEW.visible_user_ids_json)
                    WHERE type<>'integer' OR CAST(value AS INTEGER)<=0
                )
                OR EXISTS(
                    SELECT value FROM json_each(NEW.visible_user_ids_json)
                    GROUP BY value HAVING COUNT(*)>1
                )
            )
        BEGIN SELECT RAISE(ABORT,'visible_user_ids_json must contain unique positive integers'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_food_packages_required_roles_insert
        BEFORE INSERT ON food_packages
        WHEN json_valid(NEW.required_roles_json)=0
            OR json_type(NEW.required_roles_json)<>'array'
            OR EXISTS(
                SELECT 1 FROM json_each(NEW.required_roles_json)
                WHERE type<>'text' OR value NOT IN ('reasoning','vision','tool')
            )
            OR EXISTS(
                SELECT value FROM json_each(NEW.required_roles_json)
                GROUP BY value HAVING COUNT(*)>1
            )
        BEGIN SELECT RAISE(ABORT,'required_roles_json is invalid'); END""",
    """CREATE TRIGGER IF NOT EXISTS trg_food_packages_required_roles_update
        BEFORE UPDATE OF required_roles_json ON food_packages
        WHEN json_valid(NEW.required_roles_json)=0
            OR json_type(NEW.required_roles_json)<>'array'
            OR EXISTS(
                SELECT 1 FROM json_each(NEW.required_roles_json)
                WHERE type<>'text' OR value NOT IN ('reasoning','vision','tool')
            )
            OR EXISTS(
                SELECT value FROM json_each(NEW.required_roles_json)
                GROUP BY value HAVING COUNT(*)>1
            )
        BEGIN SELECT RAISE(ABORT,'required_roles_json is invalid'); END""",
)

_SEED_STATEMENTS: Final = (
    """INSERT OR IGNORE INTO food_packages
        (food_key,display_name,system_role,visibility_mode,visible_user_ids_json,enabled,archived)
        VALUES('food_emergency','保底粮','emergency','global','[]',0,0)""",
    """INSERT OR IGNORE INTO food_packages
        (food_key,display_name,system_role,visibility_mode,visible_user_ids_json,enabled,archived)
        VALUES('food_common','常用粮','common','global','[]',0,0)""",
)
