"""Owner account queries and local recovery operations."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ai_runtime.storage.data_home import get_db_path
from app.infrastructure.persistence.account_repository import (
    AccountRepository,
    LegacyAccount,
)
from app.infrastructure.persistence.account_storage_cutover import (
    ensure_account_storage_cutover,
)
from app.infrastructure.persistence.session_repository import SessionRepository
from app.infrastructure.persistence.store import (
    get_db,
    hash_password,
    migrate_db_if_needed,
)

MIN_OWNER_PASSWORD_LENGTH = 6
MAX_OWNER_PASSWORD_LENGTH = 128
MIN_OWNER_USERNAME_LENGTH = 3
MAX_OWNER_USERNAME_LENGTH = 32


class OwnerServiceError(Exception):
    """Expected Owner account operation failure."""


@dataclass(frozen=True)
class OwnerNotFoundError(OwnerServiceError):
    def __str__(self) -> str:
        return "No Owner account in database"


@dataclass(frozen=True)
class OwnerDatabaseError(OwnerServiceError):
    path: Path
    detail: str

    def __str__(self) -> str:
        return f"Owner database operation failed ({self.path}): {self.detail}"


@dataclass(frozen=True)
class InvalidOwnerInputError(OwnerServiceError):
    field: str
    detail: str

    def __str__(self) -> str:
        return f"Invalid {self.field}: {self.detail}"


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
        ensure_account_storage_cutover(str(path))
        with get_db(str(path)) as connection:
            account = AccountRepository(connection).find_owner()
    except sqlite3.DatabaseError as error:
        raise OwnerDatabaseError(path, str(error)) from error
    if account is None:
        raise OwnerNotFoundError()
    return _owner_account(account)


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
    updated: Optional[LegacyAccount] = None
    try:
        migrate_db_if_needed(str(path))
        ensure_account_storage_cutover(str(path))
        with get_db(str(path)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            repository = AccountRepository(connection)
            owner = repository.find_owner()
            if owner is None:
                raise OwnerNotFoundError()
            owner_id = owner.user_id
            if repository.username_exists(username, excluding_user_id=owner_id):
                raise InvalidOwnerInputError("Owner 登录名", "用户名已存在")
            repository.recover_owner_credentials(
                owner_id, username, password_hash, updated_at
            )
            sessions = SessionRepository(connection)
            sessions.activate_cutover()
            sessions.revoke_for_user(
                owner_id, datetime.now(timezone.utc)
            )
            updated = repository.find_by_id(owner_id)
            connection.commit()
    except OwnerServiceError:
        raise
    except sqlite3.DatabaseError as error:
        raise OwnerDatabaseError(path, str(error)) from error
    if updated is None:
        raise OwnerDatabaseError(path, "Owner 更新结果为空")
    return _owner_account(updated)


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


def _owner_account(account: LegacyAccount) -> OwnerAccount:
    return OwnerAccount(
        user_id=account.user_id,
        username=account.username,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )
