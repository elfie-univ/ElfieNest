from __future__ import annotations

from dataclasses import dataclass

from app.features.setup.model_catalog import get_setup_model
from app.infrastructure.persistence.account_repository import (
    AccountConflictError,
    AccountRepository,
)
from app.infrastructure.persistence.setup_install_repository import (
    SetupDraftRecord,
    SetupInstallRepository,
)
from app.infrastructure.persistence.store import get_db

__all__ = [
    "SetupAlreadyCompleteError",
    "create_first_owner_from_hash",
    "has_owner",
    "needs_setup",
    "save_offline_setup_draft",
]


class SetupAlreadyCompleteError(Exception):
    pass


@dataclass(frozen=True)
class OwnerAccount:
    user_id: int
    account_id: str
    display_name: str | None
    role: str = "owner"


def save_offline_setup_draft(
    db_path: str, *, use_local_ollama: bool, model_id: str | None
) -> SetupDraftRecord:
    """Validate the Setup model choice before handing the draft to storage."""
    normalized_model_id = model_id if use_local_ollama else None
    if use_local_ollama:
        if normalized_model_id is None:
            raise ValueError("启用本地 Ollama 时必须选择模型")
        get_setup_model(normalized_model_id)
    return SetupInstallRepository(db_path).save_offline_draft(
        use_local_ollama=use_local_ollama,
        model_id=normalized_model_id,
    )


def needs_setup(db_path: str) -> bool:
    return SetupInstallRepository(db_path).get().status != "completed"


def has_owner(db_path: str) -> bool:
    """Return whether the final account store already contains an Owner."""
    with get_db(db_path) as connection:
        return AccountRepository(connection).find_owner() is not None


def create_first_owner_from_hash(db_path: str, draft: SetupDraftRecord) -> OwnerAccount:
    """Create or recover the Owner from a locked draft without plaintext secrets."""
    if draft.owner_account_id is None or draft.password_hash is None:
        raise SetupAlreadyCompleteError("Setup Owner 草稿不完整")
    normalized_display_name = (
        draft.display_name.strip()
        if draft.display_name and draft.display_name.strip()
        else None
    )
    with get_db(db_path) as conn:
        accounts = AccountRepository(conn)
        accounts.begin_immediate()
        existing = accounts.find_owner()
        if existing is not None:
            conn.commit()
            return OwnerAccount(
                user_id=existing.user_id,
                account_id=existing.account_id,
                display_name=existing.display_name,
            )
        if accounts.has_any_account():
            raise SetupAlreadyCompleteError("系统已有用户，无法执行首启设置")
        try:
            user_id = accounts.create_owner(
                account_id=draft.owner_account_id,
                password_hash=draft.password_hash,
                display_name=normalized_display_name,
                avatar_color=0,
            )
        except AccountConflictError as error:
            raise SetupAlreadyCompleteError("系统已有用户，无法执行首启设置") from error
        SetupInstallRepository(db_path).mark_owner_completed(conn, user_id)
        conn.commit()
    return OwnerAccount(
        user_id=user_id,
        account_id=draft.owner_account_id.strip(),
        display_name=normalized_display_name,
    )
