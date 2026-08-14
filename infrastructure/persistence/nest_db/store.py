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
from infrastructure.persistence.layout.data_layout import ensure_final_root_layout
from infrastructure.persistence.nest_db.final_schema import create_final_nest_database
from infrastructure.persistence.nest_db.sqlite_connection import app_sqlite_connection

logger = logging.getLogger("infrastructure.persistence.nest_db.store")

_FINAL_TABLES: Final[frozenset[str]] = frozenset(
    {
        "device_audit_events",
        "elfies",
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


# ---------------------------------------------------------------------------
# Database Initialization & Seeding
# ---------------------------------------------------------------------------


def init_db(db_path: Optional[str] = None) -> str:
    """Activate the final-contract database at an explicit fresh root."""
    if db_path is None:
        db_path = str(_get_db_path())
    data_home_from_db_path(db_path)
    resolved = Path(db_path).expanduser().absolute()
    _reject_legacy_root(resolved)
    ensure_final_root_layout(resolved.parent)
    create_final_nest_database(resolved)
    logger.info("Database initialized at %s", resolved)
    return str(resolved)


def _reject_legacy_root(database_path: Path) -> None:
    inspection = inspect_data_home(database_path.parent)
    if inspection.state not in {DataHomeState.FRESH, DataHomeState.READY}:
        raise LegacyDataRootError


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
    try:
        if not database_path.exists() or database_path.stat().st_size == 0:
            return DataHomeInspection(
                state=DataHomeState.FRESH,
                home=home,
                detail="数据目录为空，可以创建新环境",
                recoverable=False,
            )
        if database_path.is_symlink():
            raise sqlite3.DatabaseError("nest.db 不能是符号链接")
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
            detail="nest.db 无法安全读取，建议先备份后创建新环境",
            recoverable=True,
        )
    if tables != _FINAL_TABLES:
        return DataHomeInspection(
            state=DataHomeState.LEGACY,
            home=home,
            detail="nest.db 使用旧版数据表结构",
            recoverable=True,
        )
    users_sql = "" if users_sql_row is None else str(users_sql_row[0] or "")
    if "roleIN('owner','user')" in "".join(users_sql.split()):
        return DataHomeInspection(
            state=DataHomeState.LEGACY,
            home=home,
            detail="nest.db 使用旧版账号结构",
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
