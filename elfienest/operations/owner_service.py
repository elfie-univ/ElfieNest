"""Owner account queries and local recovery operations."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from elfienest.persistence.store import get_db, hash_password, migrate_db_if_needed
from runtime.storage.data_home import get_db_path

MIN_OWNER_PASSWORD_LENGTH = 6
MAX_OWNER_PASSWORD_LENGTH = 128
MIN_OWNER_USERNAME_LENGTH = 3
MAX_OWNER_USERNAME_LENGTH = 32


class OwnerServiceError(Exception):
    """Expected Owner account operation failure."""


@dataclass(frozen=True)
class OwnerNotFoundError(OwnerServiceError):
    def __str__(self) -> str:
        return "数据库中没有 Owner 账户"


@dataclass(frozen=True)
class OwnerDatabaseError(OwnerServiceError):
    path: Path
    detail: str

    def __str__(self) -> str:
        return f"Owner 数据库操作失败 ({self.path}): {self.detail}"


@dataclass(frozen=True)
class InvalidOwnerInputError(OwnerServiceError):
    field: str
    detail: str

    def __str__(self) -> str:
        return f"{self.field}无效: {self.detail}"


@dataclass(frozen=True)
class OwnerAccount:
    user_id: int
    username: str
    created_at: Optional[str]
    updated_at: Optional[str]
    password_status: str = "已设置（不可查看）"


def get_owner_account(db_path: Optional[str] = None) -> OwnerAccount:
    """Read the sole Owner account without exposing its password hash."""
    path = _existing_database_path(db_path or str(get_db_path()))
    try:
        migrate_db_if_needed(str(path))
        with get_db(str(path)) as connection:
            row = connection.execute(
                "SELECT id, username, created_at, updated_at "
                "FROM users WHERE role = 'owner' ORDER BY id LIMIT 1"
            ).fetchone()
    except sqlite3.DatabaseError as error:
        raise OwnerDatabaseError(path, str(error)) from error
    if row is None:
        raise OwnerNotFoundError()
    return _account_from_row(row)


def recover_owner_account(
    db_path: str,
    username: str,
    new_password: str,
) -> OwnerAccount:
    """Atomically replace Owner login credentials while preserving its ID."""
    username = username.strip()
    _validate_username(username)
    _validate_password(new_password)
    path = _existing_database_path(db_path)
    password_hash = hash_password(new_password)
    updated_at = datetime.now(timezone.utc).isoformat()
    updated: Optional[sqlite3.Row] = None
    try:
        migrate_db_if_needed(str(path))
        with get_db(str(path)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT id FROM users WHERE role = 'owner' ORDER BY id LIMIT 1"
            ).fetchone()
            if row is None:
                raise OwnerNotFoundError()
            owner_id = int(row[0])
            conflict = connection.execute(
                "SELECT id FROM users WHERE username = ? AND id != ?",
                (username, owner_id),
            ).fetchone()
            if conflict is not None:
                raise InvalidOwnerInputError("Owner 登录名", "用户名已存在")
            connection.execute(
                "UPDATE users SET username = ?, password_hash = ?, "
                "updated_at = ? WHERE id = ? AND role = 'owner'",
                (username, password_hash, updated_at, owner_id),
            )
            connection.execute("DELETE FROM sessions WHERE user_id = ?", (owner_id,))
            updated = connection.execute(
                "SELECT id, username, created_at, updated_at FROM users WHERE id = ?",
                (owner_id,),
            ).fetchone()
            connection.commit()
    except OwnerServiceError:
        raise
    except sqlite3.DatabaseError as error:
        raise OwnerDatabaseError(path, str(error)) from error
    if updated is None:
        raise OwnerDatabaseError(path, "Owner 更新结果为空")
    return _account_from_row(updated)


def _validate_username(username: str) -> None:
    length = len(username.strip())
    if not MIN_OWNER_USERNAME_LENGTH <= length <= MAX_OWNER_USERNAME_LENGTH:
        raise InvalidOwnerInputError(
            "Owner 登录名",
            f"长度必须为 {MIN_OWNER_USERNAME_LENGTH}-{MAX_OWNER_USERNAME_LENGTH} 个字符",
        )


def _validate_password(password: str) -> None:
    length = len(password)
    if not MIN_OWNER_PASSWORD_LENGTH <= length <= MAX_OWNER_PASSWORD_LENGTH:
        raise InvalidOwnerInputError(
            "Owner 密码",
            f"长度必须为 {MIN_OWNER_PASSWORD_LENGTH}-{MAX_OWNER_PASSWORD_LENGTH} 个字符",
        )


def _existing_database_path(db_path: str) -> Path:
    path = Path(db_path).expanduser().resolve()
    if not path.is_file():
        raise OwnerDatabaseError(path, "数据库文件不存在")
    if path.stat().st_size == 0:
        raise OwnerDatabaseError(path, "数据库文件为空")
    return path


def _account_from_row(row: sqlite3.Row) -> OwnerAccount:
    return OwnerAccount(
        user_id=int(row[0]),
        username=str(row[1]),
        created_at=None if row[2] is None else str(row[2]),
        updated_at=None if row[3] is None else str(row[3]),
    )
