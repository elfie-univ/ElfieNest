"""Owner-only local user membership and adoption-limit endpoints."""

from __future__ import annotations

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing_extensions import TypedDict

from ai_runtime.storage.data_home import get_config_path
from app.features.accounts.auth import AuthenticatedUser, hash_password, require_owner
from app.features.configuration.runtime_store import read_system_section
from app.infrastructure.persistence.account_avatar_storage import (
    AvatarStorageError,
    resolve_user_avatar,
)
from app.infrastructure.persistence.account_repository import (
    AccountRepository,
    LegacyAccount,
)
from app.infrastructure.persistence.session_repository import SessionRepository
from app.infrastructure.persistence.store import get_db

logger = logging.getLogger("app.interfaces.api.owner_user_routes")
router = APIRouter(prefix="/api/owner/users", tags=["owner-users"])


class OwnerUserView(TypedDict):
    id: int
    username: str
    display_name: str
    role: Literal["user"]
    created_at: str
    elfie_count: int
    elfie_quota_override: Optional[int]
    effective_elfie_limit: int
    online_status: Literal["unknown"]
    avatar_url: Optional[str]


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1)
    role: Literal["user"] = "user"

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("用户名不能为空")
        return normalized


class QuotaUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    elfie_quota_override: Optional[int] = Field(default=None, ge=1, le=32)


def _system_limit() -> int:
    settings = read_system_section(get_config_path(), "adoption")
    return int(settings.get("max_elfies_per_user", 3))


def _project(account: LegacyAccount, system_limit: int) -> OwnerUserView:
    override = account.elfie_limit
    user_id = account.user_id
    return {
        "id": user_id,
        "username": account.username,
        "display_name": account.nickname or account.username,
        "role": "user",
        "created_at": str(account.created_at),
        "elfie_count": account.elfie_count,
        "elfie_quota_override": override,
        "effective_elfie_limit": system_limit if override is None else override,
        "online_status": "unknown",
        "avatar_url": f"/api/owner/users/{user_id}/avatar"
        if account.avatar_path
        else None,
    }


def _load_user(db_path: str, user_id: int, system_limit: int) -> OwnerUserView:
    with get_db(db_path) as connection:
        account = AccountRepository(connection).find_by_id(user_id)
    if account is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if account.role == "owner":
        raise HTTPException(status_code=403, detail="Owner 账户只能在个人设置中管理")
    return _project(account, system_limit)


@router.get("")
async def list_users(
    request: Request,
    owner: AuthenticatedUser = Depends(require_owner),  # noqa: B008
) -> list[OwnerUserView]:
    system_limit = _system_limit()
    with get_db(request.app.state.db_path) as connection:
        accounts = AccountRepository(connection).list_excluding(int(owner["id"]))
    return [_project(account, system_limit) for account in accounts]


@router.post("", status_code=201)
async def create_user(
    body: CreateUserRequest,
    request: Request,
    owner: AuthenticatedUser = Depends(require_owner),  # noqa: B008
) -> OwnerUserView:
    _ = owner
    with get_db(request.app.state.db_path) as connection:
        repository = AccountRepository(connection)
        if repository.username_exists(body.username):
            raise HTTPException(status_code=409, detail="用户名已存在")
        user_id = repository.create_user(
            body.username, hash_password(body.password)
        )
        connection.commit()
    return _load_user(request.app.state.db_path, user_id, _system_limit())


@router.put("/{user_id}")
async def update_quota(
    user_id: int,
    body: QuotaUpdateRequest,
    request: Request,
    owner: AuthenticatedUser = Depends(require_owner),  # noqa: B008
) -> OwnerUserView:
    _ = owner
    if "elfie_quota_override" not in body.model_fields_set:
        raise HTTPException(status_code=422, detail="必须提供 elfie_quota_override")
    _load_user(request.app.state.db_path, user_id, _system_limit())
    with get_db(request.app.state.db_path) as connection:
        AccountRepository(connection).update_quota(
            user_id, body.elfie_quota_override
        )
        connection.commit()
    return _load_user(request.app.state.db_path, user_id, _system_limit())


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    request: Request,
    owner: AuthenticatedUser = Depends(require_owner),  # noqa: B008
) -> dict[str, str]:
    _ = owner
    user = _load_user(request.app.state.db_path, user_id, _system_limit())
    if user["elfie_count"] > 0:
        raise HTTPException(
            status_code=409, detail="该用户仍有名下精灵，请先处理精灵归属后再移除"
        )
    with get_db(request.app.state.db_path) as connection:
        SessionRepository(connection).delete_for_user(user_id)
        AccountRepository(connection).delete(user_id)
        connection.commit()
    logger.info("Owner removed user %s (id=%d)", user["username"], user_id)
    return {"detail": f"用户 {user['username']} 已移除"}


@router.get("/{user_id}/avatar")
async def user_avatar(
    user_id: int,
    request: Request,
    owner: AuthenticatedUser = Depends(require_owner),  # noqa: B008
) -> FileResponse:
    _ = owner
    with get_db(request.app.state.db_path) as connection:
        account = AccountRepository(connection).find_by_id(user_id)
    if account is None or account.role == "owner" or not account.avatar_path:
        raise HTTPException(status_code=404, detail="用户头像不存在")
    try:
        candidate = resolve_user_avatar(
            request.app.state.db_path, user_id, account.avatar_path
        )
    except AvatarStorageError:
        raise HTTPException(
            status_code=404, detail="用户头像文件不存在"
        ) from None
    return FileResponse(candidate, headers={"Cache-Control": "no-store"})
