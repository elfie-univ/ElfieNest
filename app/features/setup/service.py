from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.features.accounts.auth import create_session, generate_csrf_token
from app.features.setup.progress import (
    SetupProgress,
    SetupStep,
    complete_setup_step,
    get_setup_progress,
    mark_owner_step_completed,
    record_setup_task_failure,
)
from app.infrastructure.persistence.store import get_db, hash_password

__all__ = [
    "SetupAlreadyCompleteError",
    "SetupProgress",
    "SetupResult",
    "SetupStep",
    "complete_setup_step",
    "create_first_owner",
    "create_first_owner_account",
    "get_setup_progress",
    "needs_setup",
    "record_setup_task_failure",
]


class SetupAlreadyCompleteError(Exception):
    pass


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
    return not get_setup_progress(db_path).complete


def create_first_owner_account(
    db_path: str,
    *,
    username: str,
    password: str,
    display_name: str | None = None,
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
                (
                    username,
                    hash_password(password),
                    display_name.strip()
                    if display_name and display_name.strip()
                    else username,
                    avatar_color,
                ),
            )
        except sqlite3.IntegrityError as error:
            raise SetupAlreadyCompleteError("系统已有用户，无法执行首启设置") from error
        user_id = cursor.lastrowid
        if user_id is None:
            raise SetupAlreadyCompleteError("Owner 账户创建结果无效")
        mark_owner_step_completed(conn, int(user_id))
        conn.commit()
    if user_id is None:
        raise SetupAlreadyCompleteError("Owner 账户创建结果无效")
    return OwnerAccount(user_id=int(user_id), username=username)


def create_first_owner(
    db_path: str,
    *,
    username: str,
    password: str,
    display_name: str | None = None,
    avatar_color: int = 0,
) -> SetupResult:
    """Create the first Owner and issue its initial Web session."""
    account = create_first_owner_account(
        db_path,
        username=username,
        password=password,
        display_name=display_name,
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
