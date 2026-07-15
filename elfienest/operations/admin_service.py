"""管理员账户查询与本地密码恢复领域服务。"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final, FrozenSet, Iterator, Optional, Tuple

from elfienest.persistence.store import hash_password

MIN_PASSWORD_LENGTH: Final = 6
MAX_PASSWORD_LENGTH: Final = 128
_REQUIRED_USER_COLUMNS: Final[FrozenSet[str]] = frozenset(
    {"id", "username", "password_hash", "role"}
)
_REQUIRED_SESSION_COLUMNS: Final[FrozenSet[str]] = frozenset(
    {"token", "user_id", "expires_at"}
)


class AdminServiceError(Exception):
    """管理员领域服务可预期错误的基类。"""


@dataclass(frozen=True)
class DatabaseUnavailableError(AdminServiceError):
    path: Path

    def __str__(self) -> str:
        return f"数据库文件不可用: {self.path}"


@dataclass(frozen=True)
class DatabaseSchemaError(AdminServiceError):
    path: Path
    detail: str

    def __str__(self) -> str:
        return f"数据库 schema 无效 ({self.path}): {self.detail}"


@dataclass(frozen=True)
class DatabaseOperationError(AdminServiceError):
    path: Path
    detail: str

    def __str__(self) -> str:
        return f"数据库操作失败 ({self.path}): {self.detail}"


@dataclass(frozen=True)
class InvalidPasswordError(AdminServiceError):
    actual_length: int
    minimum_length: int = MIN_PASSWORD_LENGTH
    maximum_length: int = MAX_PASSWORD_LENGTH

    def __str__(self) -> str:
        return (
            f"新密码长度必须为 {self.minimum_length}-{self.maximum_length} 个字符，"
            f"当前为 {self.actual_length} 个字符"
        )


@dataclass(frozen=True)
class AdminNotFoundError(AdminServiceError):
    username: Optional[str]

    def __str__(self) -> str:
        if self.username is None:
            return "数据库中没有管理员账户"
        return f"管理员账户不存在: {self.username}"


@dataclass(frozen=True)
class NotAdministratorError(AdminServiceError):
    username: str

    def __str__(self) -> str:
        return f"账户不是管理员: {self.username}"


@dataclass(frozen=True)
class AdminSelectionRequiredError(AdminServiceError):
    usernames: Tuple[str, ...]

    def __str__(self) -> str:
        return "存在多个管理员，请明确指定用户名: " + ", ".join(self.usernames)


@dataclass(frozen=True)
class AdminAccount:
    user_id: int
    username: str
    created_at: Optional[str]


def list_admin_accounts(db_path: str) -> Tuple[AdminAccount, ...]:
    """返回数据库中的管理员账户，不暴露密码或会话信息。"""
    database_path = _existing_database_path(db_path)
    with _connect_existing(database_path) as connection:
        _validate_schema(connection, database_path)
        try:
            rows = connection.execute(
                _admin_select(connection) + " ORDER BY username"
            ).fetchall()
        except sqlite3.DatabaseError as error:
            raise DatabaseOperationError(database_path, str(error)) from error
    return tuple(_account_from_row(row) for row in rows)


def reset_admin_password(
    db_path: str,
    username: Optional[str],
    new_password: str,
) -> AdminAccount:
    """原子更新一个管理员密码，并撤销该账户的全部 session。"""
    _validate_password(new_password)
    database_path = _existing_database_path(db_path)
    password_hash = hash_password(new_password)

    with _connect_existing(database_path) as connection:
        _validate_schema(connection, database_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            _validate_schema(connection, database_path)
            account = _select_admin(connection, username)
            update = connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = ? AND role = 'admin'",
                (password_hash, account.user_id),
            )
            if update.rowcount != 1:
                raise NotAdministratorError(account.username)
            connection.execute(
                "DELETE FROM sessions WHERE user_id = ?", (account.user_id,)
            )
            connection.commit()
        except AdminServiceError:
            connection.rollback()
            raise
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise DatabaseOperationError(database_path, str(error)) from error
    return account


def _validate_password(password: str) -> None:
    password_length = len(password)
    if not MIN_PASSWORD_LENGTH <= password_length <= MAX_PASSWORD_LENGTH:
        raise InvalidPasswordError(password_length)


def _existing_database_path(db_path: str) -> Path:
    database_path = Path(db_path).expanduser().resolve()
    if not database_path.is_file():
        raise DatabaseUnavailableError(database_path)
    return database_path


@contextmanager
def _connect_existing(database_path: Path) -> Iterator[sqlite3.Connection]:
    try:
        connection = sqlite3.connect(
            f"{database_path.as_uri()}?mode=rw",
            uri=True,
        )
    except sqlite3.Error as error:
        raise DatabaseUnavailableError(database_path) from error
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
    finally:
        connection.close()


def _validate_schema(connection: sqlite3.Connection, database_path: Path) -> None:
    try:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if "users" not in tables or "sessions" not in tables:
            raise DatabaseSchemaError(database_path, "缺少 users 或 sessions 数据表")
        user_columns = _table_columns(connection, "users")
        session_columns = _table_columns(connection, "sessions")
    except sqlite3.DatabaseError as error:
        raise DatabaseSchemaError(database_path, str(error)) from error

    missing_users = _REQUIRED_USER_COLUMNS - user_columns
    missing_sessions = _REQUIRED_SESSION_COLUMNS - session_columns
    if missing_users or missing_sessions:
        detail = (
            f"users 缺少 {sorted(missing_users)}; "
            f"sessions 缺少 {sorted(missing_sessions)}"
        )
        raise DatabaseSchemaError(database_path, detail)


def _table_columns(connection: sqlite3.Connection, table_name: str) -> FrozenSet[str]:
    return frozenset(
        str(row[1]) for row in connection.execute(f"PRAGMA table_info({table_name})")
    )


def _admin_select(connection: sqlite3.Connection) -> str:
    created_at = (
        "created_at" if "created_at" in _table_columns(connection, "users") else "NULL"
    )
    return (
        f"SELECT id, username, {created_at} AS created_at "
        "FROM users WHERE role = 'admin'"
    )


def _select_admin(
    connection: sqlite3.Connection, username: Optional[str]
) -> AdminAccount:
    if username is None:
        rows = connection.execute(
            _admin_select(connection) + " ORDER BY username"
        ).fetchall()
        if not rows:
            raise AdminNotFoundError(None)
        if len(rows) > 1:
            raise AdminSelectionRequiredError(tuple(str(row[1]) for row in rows))
        return _account_from_row(rows[0])

    row = connection.execute(
        "SELECT id, username, role, "
        + (
            "created_at"
            if "created_at" in _table_columns(connection, "users")
            else "NULL"
        )
        + " AS created_at FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if row is None:
        raise AdminNotFoundError(username)
    if str(row[2]) != "admin":
        raise NotAdministratorError(username)
    return AdminAccount(
        user_id=int(row[0]),
        username=str(row[1]),
        created_at=None if row[3] is None else str(row[3]),
    )


def _account_from_row(row: sqlite3.Row) -> AdminAccount:
    return AdminAccount(
        user_id=int(row[0]),
        username=str(row[1]),
        created_at=None if row[2] is None else str(row[2]),
    )
