from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from elfienest.accounts.auth import create_session, generate_csrf_token
from elfienest.persistence.store import get_db, hash_password


class SetupAlreadyCompleteError(Exception):
    pass


@dataclass(frozen=True)
class AdminAccount:
    user_id: int
    username: str
    role: str


@dataclass(frozen=True)
class OwnerAccount:
    user_id: int
    username: str
    role: str = "owner"


@dataclass(frozen=True)
class SetupResult:
    user_id: int
    username: str
    role: str
    session_token: str
    csrf_token: str


def needs_setup(db_path: str) -> bool:
    with get_db(db_path) as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM users")
        return cursor.fetchone()[0] == 0


def create_first_admin_account(
    db_path: str,
    *,
    username: str,
    password: str,
    avatar_color: int = 0,
) -> AdminAccount:
    with get_db(db_path) as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] > 0:
            raise SetupAlreadyCompleteError("系统已有用户，无法执行首启设置")

        cursor = conn.execute(
            "INSERT INTO users "
            "(username, password_hash, role, nickname, avatar_color, avatar_kind) "
            "VALUES (?, ?, 'admin', ?, ?, 'initials')",
            (username, hash_password(password), username, avatar_color),
        )
        user_id = cursor.lastrowid
        conn.commit()

    return AdminAccount(
        user_id=user_id,
        username=username,
        role="admin",
    )


def create_first_admin(
    db_path: str,
    *,
    username: str,
    password: str,
    avatar_color: int = 0,
) -> SetupResult:
    account = create_first_admin_account(
        db_path,
        username=username,
        password=password,
        avatar_color=avatar_color,
    )
    session_token = create_session(account.user_id, db_path)
    return SetupResult(
        user_id=account.user_id,
        username=account.username,
        role=account.role,
        session_token=session_token,
        csrf_token=generate_csrf_token(session_token),
    )


def create_first_owner_account(
    db_path: str,
    *,
    username: str,
    password: str,
    avatar_color: int = 0,
) -> OwnerAccount:
    """Create the single product Owner during first-time setup."""
    with get_db(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
            raise SetupAlreadyCompleteError("系统已有用户，无法执行首启设置")
        try:
            cursor = conn.execute(
                "INSERT INTO users "
                "(username, password_hash, role, nickname, avatar_color, avatar_kind) "
                "VALUES (?, ?, 'owner', ?, ?, 'initials')",
                (username, hash_password(password), username, avatar_color),
            )
        except sqlite3.IntegrityError as error:
            raise SetupAlreadyCompleteError("系统已有用户，无法执行首启设置") from error
        user_id = cursor.lastrowid
        conn.commit()
    if user_id is None:
        raise SetupAlreadyCompleteError("Owner 账户创建结果无效")
    return OwnerAccount(user_id=int(user_id), username=username)


def create_first_owner(
    db_path: str,
    *,
    username: str,
    password: str,
    avatar_color: int = 0,
) -> SetupResult:
    """Create the first Owner and issue its initial Web session."""
    account = create_first_owner_account(
        db_path,
        username=username,
        password=password,
        avatar_color=avatar_color,
    )
    session_token = create_session(account.user_id, db_path)
    return SetupResult(
        user_id=account.user_id,
        username=account.username,
        role=account.role,
        session_token=session_token,
        csrf_token=generate_csrf_token(session_token),
    )
