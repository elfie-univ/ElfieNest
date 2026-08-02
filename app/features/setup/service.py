from __future__ import annotations

from dataclasses import dataclass

from app.features.accounts.auth import create_session, generate_csrf_token
from app.features.setup.progress import (
    SetupProgress,
    SetupStep,
    complete_setup_step,
    get_setup_progress,
    record_setup_task_failure,
)
from app.infrastructure.persistence.account_repository import (
    AccountConflictError,
    AccountRepository,
)
from app.infrastructure.persistence.installation_repository import (
    InstallationRepository,
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
    account_id: str
    display_name: str | None
    role: str = "owner"


@dataclass(frozen=True)
class SetupResult:
    __slots__ = (
        "user_id",
        "account_id",
        "display_name",
        "role",
        "session_token",
        "csrf_token",
    )

    user_id: int
    account_id: str
    display_name: str | None
    role: str
    session_token: str
    csrf_token: str


def needs_setup(db_path: str) -> bool:
    return not get_setup_progress(db_path).complete


def create_first_owner_account(
    db_path: str,
    *,
    account_id: str,
    password: str,
    display_name: str | None = None,
    avatar_color: int = 0,
) -> OwnerAccount:
    """Create the single product Owner during first-time setup."""
    normalized_display_name = (
        display_name.strip() if display_name and display_name.strip() else None
    )
    with get_db(db_path) as conn:
        accounts = AccountRepository(conn)
        accounts.begin_immediate()
        if accounts.has_any_account():
            raise SetupAlreadyCompleteError("系统已有用户，无法执行首启设置")
        try:
            user_id = accounts.create_owner(
                account_id=account_id,
                password_hash=hash_password(password),
                display_name=normalized_display_name,
                avatar_color=avatar_color,
            )
        except AccountConflictError as error:
            raise SetupAlreadyCompleteError("系统已有用户，无法执行首启设置") from error
        InstallationRepository(db_path).mark_owner_completed(conn, user_id)
        conn.commit()
    return OwnerAccount(
        user_id=user_id,
        account_id=account_id.strip(),
        display_name=normalized_display_name,
    )


def create_first_owner(
    db_path: str,
    *,
    account_id: str,
    password: str,
    display_name: str | None = None,
    avatar_color: int = 0,
) -> SetupResult:
    """Create the first Owner and issue its initial Web session."""
    account = create_first_owner_account(
        db_path,
        account_id=account_id,
        password=password,
        display_name=display_name,
        avatar_color=avatar_color,
    )
    session_token = create_session(account.user_id, db_path)
    return SetupResult(
        user_id=account.user_id,
        account_id=account.account_id,
        display_name=account.display_name,
        role=account.role,
        session_token=session_token,
        csrf_token=generate_csrf_token(session_token),
    )
