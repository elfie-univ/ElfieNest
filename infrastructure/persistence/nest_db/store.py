"""Final root database activation, connection policy, and Owner seed."""

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Final, Iterator, Optional

from app.features.accounts import hash_password
from app.features.accounts import verify_password as verify_password
from app.orchestration.lifecycle.ports import DataHomeInspection, DataHomeState
from infrastructure.persistence.layout.data_home import data_home_from_db_path
from infrastructure.persistence.layout.data_home import get_db_path as _get_db_path
from infrastructure.persistence.layout.data_layout import (
    ensure_final_root_layout,
    final_root_layout,
)
from infrastructure.persistence.nest_db.final_schema import (
    create_final_nest_database,
    missing_final_schema_columns,
    repair_final_nest_database,
    unexpected_final_schema_columns,
    unsupported_final_schema_columns,
)
from infrastructure.persistence.nest_db.sqlite_connection import app_sqlite_connection

logger = logging.getLogger("infrastructure.persistence.nest_db.store")

_FINAL_TABLES: Final[frozenset[str]] = frozenset(
    {
        "device_audit_events",
        "elfies",
        "resident_admissions",
        "embodiment_sessions",
        "external_bodies",
        "food_packages",
        "local_installations",
        "nest_settings",
        "sessions",
        "users",
    }
)
_RETIRED_ROOT_ENTRIES: Final[tuple[str, ...]] = (
    "backups",
    "cache",
    "developer",
    "files",
    "models",
    "sessions",
    "skills",
    "validations",
)


class LegacyDataRootError(RuntimeError):
    """The selected root contains data that this MVP does not migrate."""

    __slots__ = ()

    def __str__(self) -> str:
        return "检测到旧 ElfieNest 数据根；请先备份后重建。不会自动迁移或删除。"


class IncompatibleDatabaseError(LegacyDataRootError):
    """The database is readable but does not satisfy the current schema contract."""

    __slots__ = ("detail",)

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)

    def __str__(self) -> str:
        return f"{self.detail}；请先备份后重建。不会自动迁移或删除。"


# ---------------------------------------------------------------------------
# Database Initialization & Seeding
# ---------------------------------------------------------------------------


def init_db(db_path: Optional[str] = None) -> str:
    """Activate or minimally repair the final-contract database."""
    if db_path is None:
        db_path = str(_get_db_path())
    data_home_from_db_path(db_path)
    resolved = Path(db_path).expanduser().absolute()
    inspection = _reject_legacy_root(resolved)
    ensure_final_root_layout(resolved.parent)
    if inspection.state is DataHomeState.PARTIAL:
        repair_final_nest_database(resolved)
    else:
        create_final_nest_database(resolved)
    logger.info("Database initialized at %s", resolved)
    return str(resolved)


def _reject_legacy_root(database_path: Path) -> DataHomeInspection:
    inspection = inspect_data_home(database_path.parent)
    if inspection.state not in {
        DataHomeState.FRESH,
        DataHomeState.PARTIAL,
        DataHomeState.READY,
    }:
        if inspection.detail.startswith("数据库结构与当前版本不兼容"):
            raise IncompatibleDatabaseError(inspection.detail)
        raise LegacyDataRootError
    return inspection


def repair_data_home(data_home: Path) -> DataHomeInspection:
    """Repair only a fresh/partial/current root in place, without preserving copies."""
    inspection = inspect_data_home(data_home)
    if inspection.state not in {
        DataHomeState.FRESH,
        DataHomeState.PARTIAL,
        DataHomeState.READY,
    }:
        if inspection.detail.startswith("数据库结构与当前版本不兼容"):
            raise IncompatibleDatabaseError(inspection.detail)
        raise LegacyDataRootError

    if inspection.state is DataHomeState.READY:
        return inspection

    home = inspection.home
    ensure_final_root_layout(home)
    try:
        repair_final_nest_database(home / "nest.db")
    except (sqlite3.DatabaseError, RuntimeError) as error:
        detail = str(error)
        if not detail.startswith("数据库结构与当前版本不兼容"):
            detail = "数据库结构与当前版本不兼容：最小修复失败"
        raise IncompatibleDatabaseError(detail) from error

    repaired = inspect_data_home(home)
    if repaired.state is not DataHomeState.READY:
        if repaired.detail.startswith("数据库结构与当前版本不兼容"):
            raise IncompatibleDatabaseError(repaired.detail)
        raise LegacyDataRootError
    return repaired


def _has_product_entries(home: Path) -> bool:
    """Ignore only the optional source CLI subtree during root inspection."""
    layout = final_root_layout(home)
    runtime_dir = layout.runtime_state.parent
    for entry in home.iterdir():
        if entry != runtime_dir:
            return True
        if entry.is_symlink() or not entry.is_dir():
            return True
        for runtime_entry in entry.iterdir():
            if runtime_entry != layout.source_cli_state:
                return True
            if runtime_entry.is_symlink() or not runtime_entry.is_dir():
                return True
    return False


def inspect_data_home(data_home: Path) -> DataHomeInspection:
    """Classify a selected root without creating, migrating, or deleting files."""
    raw_home = data_home.expanduser()
    if raw_home.is_symlink() or (raw_home.exists() and not raw_home.is_dir()):
        return DataHomeInspection(
            state=DataHomeState.PERMISSION,
            home=raw_home.resolve(strict=False),
            detail="数据目录必须是当前用户可访问的真实目录",
            recoverable=False,
        )
    home = raw_home.resolve(strict=False)
    if not home.exists():
        return DataHomeInspection(
            state=DataHomeState.FRESH,
            home=home,
            detail="尚未创建数据目录",
            recoverable=False,
        )
    if any((home / entry).exists() for entry in _RETIRED_ROOT_ENTRIES):
        return DataHomeInspection(
            state=DataHomeState.LEGACY,
            home=home,
            detail="检测到旧版 ElfieNest 数据目录结构",
            recoverable=True,
        )
    database_path = home / "nest.db"
    if database_path.is_symlink():
        return DataHomeInspection(
            state=DataHomeState.PERMISSION,
            home=home,
            detail="nest.db 不能是符号链接",
            recoverable=False,
        )
    try:
        if not database_path.exists() or database_path.stat().st_size == 0:
            has_residual_entries = _has_product_entries(home)
            return DataHomeInspection(
                state=(
                    DataHomeState.PARTIAL
                    if has_residual_entries
                    else DataHomeState.FRESH
                ),
                home=home,
                detail=(
                    "检测到未完成的数据初始化，启动时可以补齐"
                    if has_residual_entries
                    else "尚未创建数据目录"
                ),
                recoverable=False,
            )
        uri = f"{database_path.as_uri()}?mode=ro&immutable=1"
        with sqlite3.connect(uri, uri=True) as connection:
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            users_sql_row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
            ).fetchone()
            if not tables.issubset(_FINAL_TABLES):
                return DataHomeInspection(
                    state=DataHomeState.LEGACY,
                    home=home,
                    detail="数据库结构与当前版本不兼容：数据表集合不是当前版本契约",
                    recoverable=True,
                )
            if tables != _FINAL_TABLES:
                missing_tables = ", ".join(sorted(_FINAL_TABLES - tables))
                return DataHomeInspection(
                    state=DataHomeState.PARTIAL,
                    home=home,
                    detail="启动时可以补齐缺少的当前数据表：" + missing_tables,
                    recoverable=False,
                )
            users_sql = "" if users_sql_row is None else str(users_sql_row[0] or "")
            if "roleIN('owner','user')" in "".join(users_sql.split()):
                return DataHomeInspection(
                    state=DataHomeState.LEGACY,
                    home=home,
                    detail="数据库结构与当前版本不兼容：users.role 仍是旧版账号约束",
                    recoverable=True,
                )
            unexpected_columns = unexpected_final_schema_columns(connection)
            if unexpected_columns:
                return DataHomeInspection(
                    state=DataHomeState.LEGACY,
                    home=home,
                    detail=(
                        "数据库结构与当前版本不兼容：存在当前版本不认识的字段 "
                        + ", ".join(unexpected_columns)
                    ),
                    recoverable=True,
                )
            missing_columns = missing_final_schema_columns(connection)
            if missing_columns:
                unsupported_columns = unsupported_final_schema_columns(missing_columns)
                if unsupported_columns:
                    return DataHomeInspection(
                        state=DataHomeState.LEGACY,
                        home=home,
                        detail=(
                            "数据库结构与当前版本不兼容：缺少不可安全补齐的字段 "
                            + ", ".join(unsupported_columns)
                        ),
                        recoverable=True,
                    )
                return DataHomeInspection(
                    state=DataHomeState.PARTIAL,
                    home=home,
                    detail=(
                        "启动时可以补齐缺少的当前字段 " + ", ".join(missing_columns)
                    ),
                    recoverable=False,
                )
    except PermissionError:
        return DataHomeInspection(
            state=DataHomeState.PERMISSION,
            home=home,
            detail="没有权限读取当前数据目录，请检查目录权限",
            recoverable=False,
        )
    except (OSError, sqlite3.DatabaseError):
        return DataHomeInspection(
            state=DataHomeState.CORRUPT,
            home=home,
            detail="数据库无法安全读取，无法确认是否兼容；建议先备份后创建新环境",
            recoverable=True,
        )
    return DataHomeInspection(
        state=DataHomeState.READY,
        home=home,
        detail="数据目录符合当前版本契约",
        recoverable=False,
    )


def seed_initial_owner_if_env_set(
    db_path: Optional[str] = None,
    account_id_env: str = "OWNER_ACCOUNT_ID",
    password_env: str = "OWNER_PASSWORD",
) -> bool:
    """从 Owner 环境变量创建唯一 Owner 账户。"""
    return _seed_initial_account_from_env(
        db_path,
        account_id_env=account_id_env,
        password_env=password_env,
        role="owner",
    )


def _seed_initial_account_from_env(
    db_path: Optional[str],
    *,
    account_id_env: str,
    password_env: str,
    role: str,
) -> bool:
    if db_path is None:
        db_path = str(_get_db_path())
    account_id = os.environ.get(account_id_env, "")
    password = os.environ.get(password_env, "")

    if not account_id or not password:
        return False

    with get_db(db_path) as conn:
        if role == "owner":
            conn.execute("BEGIN IMMEDIATE")
        # 检查是否已存在
        cursor = conn.execute(
            "SELECT id FROM users WHERE account_id = ?", (account_id,)
        )
        if cursor.fetchone() is not None:
            return False

        pw_hash = hash_password(password)
        if role == "owner":
            owner = conn.execute(
                "SELECT id FROM users WHERE role = 'owner' LIMIT 1"
            ).fetchone()
            if owner is not None:
                return False
        try:
            conn.execute(
                "INSERT INTO users (account_id, password_hash, role) VALUES (?, ?, ?)",
                (account_id, pw_hash, role),
            )
        except sqlite3.IntegrityError:
            return False
        conn.commit()
        logger.info("从环境变量创建了初始 %s: %s", role, account_id)
        return True


# ---------------------------------------------------------------------------
# Connection Context Manager
# ---------------------------------------------------------------------------


@contextmanager
def get_db(db_path: Optional[str] = None) -> Iterator[sqlite3.Connection]:
    """Context manager that yields a new SQLite connection and closes it on exit.

    Every call opens a fresh connection — this is intentional to avoid
    cross-thread sharing issues with FastAPI.

    Args:
        db_path: Path to the SQLite database file. Defaults to
            ``ELFIE_HOME/nest.db``.

    Yields:
        An open :class:`sqlite3.Connection` with ``row_factory`` set to
        :class:`sqlite3.Row` and ``PRAGMA foreign_keys = ON``.
    """
    if db_path is None:
        db_path = str(_get_db_path())

    with app_sqlite_connection(db_path) as connection:
        yield connection


# ---------------------------------------------------------------------------
# Query Helpers
# ---------------------------------------------------------------------------


def count_elfies_by_owner(user_id: int, db_path: Optional[str] = None) -> int:
    """Return the number of elfies currently owned by *user_id*.

    Used by the adoption endpoint to enforce the per-user limit (max 3).

    Args:
        user_id: The user's database ``id``.
        db_path: Path to the SQLite database file.  Defaults to ``~/.elfienest/nest.db``.

    Returns:
        Elfie count for the given owner.
    """
    with get_db(db_path) as db:
        cursor = db.execute(
            "SELECT COUNT(*) AS cnt FROM elfies WHERE owner_user_id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        return row["cnt"] if row else 0
