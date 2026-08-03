"""Manager local user membership and adoption-limit endpoints."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing_extensions import TypedDict

from ai_runtime.storage.data_home import data_home_from_db_path
from ai_runtime.storage.data_layout import final_root_layout
from app.features.accounts.auth import AuthenticatedUser, require_manager
from app.features.accounts.password_policy import validate_password_strength
from app.features.accounts.roles import AccountRole, can_manage_role, parse_account_role
from app.features.administration.member_service import (
    MemberAccountCapacityError,
    MemberAccountConflictError,
    MemberService,
)
from app.features.configuration.runtime_store import read_system_section
from app.infrastructure.persistence.interface_query_repository import (
    InterfaceQueryRepository,
    InterfaceUserRecord,
    MemberMutationTargetError,
)

logger = logging.getLogger("app.interfaces.api.owner_user_routes")
router = APIRouter(prefix="/api/owner/users", tags=["owner-users"])


class OwnerUserView(TypedDict):
    user_id: int
    account_id: str
    display_name: Optional[str]
    role: AccountRole
    gender: str
    birth_date: Optional[str]
    presence: Literal["online", "away", "offline"]
    last_seen_at: Optional[str]
    language: str
    created_at: str
    elfie_count: int
    elfie_quota_override: Optional[int]
    effective_elfie_limit: int
    avatar_url: Optional[str]


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    account_id: str
    display_name: Optional[str] = None
    password: str = Field(min_length=6, max_length=128)
    role: Literal["admin", "user"]

    @field_validator("account_id")
    @classmethod
    def normalize_account_id(cls, value: str) -> str:
        normalized = value.strip()
        if not 3 <= len(normalized) <= 32:
            message = "登录账号去除首尾空格后必须为 3-32 个字符"
            raise ValueError(message)
        return normalized

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > 64:
            message = "显示名称最多 64 个字符"
            raise ValueError(message)
        return normalized

    @field_validator("password")
    @classmethod
    def reject_blank_password(cls, value: str) -> str:
        return validate_password_strength(value)


class QuotaUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    elfie_quota_override: Optional[int] = Field(default=None, ge=1, le=32)


def _system_limit(db_path: str) -> int:
    settings = read_system_section(
        final_root_layout(data_home_from_db_path(db_path)).runtime_config,
        "adoption",
    )
    return int(settings.get("max_elfies_per_user", 3))


def _project(row: InterfaceUserRecord, system_limit: int) -> OwnerUserView:
    override = row.elfie_limit
    user_id = row.user_id
    if row.presence not in {"online", "away", "offline"}:
        raise RuntimeError("invalid persisted presence")
    role = parse_account_role(row.role)
    presence = cast(Literal["online", "away", "offline"], row.presence)
    return {
        "user_id": user_id,
        "account_id": row.account_id,
        "display_name": row.display_name,
        "role": role,
        "gender": row.gender or "male",
        "birth_date": row.birth_date,
        "presence": presence,
        "last_seen_at": row.last_seen_at,
        "language": row.language,
        "created_at": row.created_at,
        "elfie_count": row.elfie_count,
        "elfie_quota_override": override,
        "effective_elfie_limit": system_limit if override is None else override,
        "avatar_url": f"/api/owner/users/{user_id}/avatar" if row.avatar_path else None,
    }


def _load_user(db_path: str, user_id: int, system_limit: int) -> OwnerUserView:
    row = InterfaceQueryRepository(db_path).get_user(user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return _project(row, system_limit)


def _load_managed_member(
    db_path: str,
    user_id: int,
    system_limit: int,
    actor_role: AccountRole,
) -> OwnerUserView:
    user = _load_user(db_path, user_id, system_limit)
    if not can_manage_role(actor_role, user["role"]):
        raise HTTPException(status_code=403, detail="只能管理低于当前角色的账号")
    return user


@router.get("")
async def list_users(
    request: Request,
    owner: AuthenticatedUser = Depends(require_manager),  # noqa: B008
) -> list[OwnerUserView]:
    system_limit = _system_limit(request.app.state.db_path)
    rows = InterfaceQueryRepository(request.app.state.db_path).list_all_users()
    return [_project(row, system_limit) for row in rows]


@router.post("", status_code=201)
async def create_user(
    body: CreateUserRequest,
    request: Request,
    owner: AuthenticatedUser = Depends(require_manager),  # noqa: B008
) -> OwnerUserView:
    if body.role == "admin" and owner["role"] != "owner":
        raise HTTPException(status_code=403, detail="只有 Owner 可以新增 Admin")
    try:
        user_id = MemberService(request.app.state.db_path).create_member(
            account_id=body.account_id,
            display_name=body.display_name,
            password=body.password,
            role=body.role,
        )
    except MemberAccountConflictError as error:
        raise HTTPException(status_code=409, detail="登录账号已存在") from error
    except MemberAccountCapacityError as error:
        raise HTTPException(
            status_code=409, detail="账号人数或 Admin 名额已满"
        ) from error
    return _load_user(
        request.app.state.db_path,
        user_id,
        _system_limit(request.app.state.db_path),
    )


@router.put("/{user_id}")
async def update_quota(
    user_id: int,
    body: QuotaUpdateRequest,
    request: Request,
    owner: AuthenticatedUser = Depends(require_manager),  # noqa: B008
) -> OwnerUserView:
    if "elfie_quota_override" not in body.model_fields_set:
        raise HTTPException(status_code=422, detail="必须提供 elfie_quota_override")
    system_limit = _system_limit(request.app.state.db_path)
    _load_managed_member(
        request.app.state.db_path,
        user_id,
        system_limit,
        owner["role"],
    )
    updated = InterfaceQueryRepository(request.app.state.db_path).update_member_limit(
        user_id, body.elfie_quota_override
    )
    if not updated:
        raise HTTPException(status_code=409, detail="目标账号已无法管理")
    return _load_managed_member(
        request.app.state.db_path,
        user_id,
        system_limit,
        owner["role"],
    )


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    request: Request,
    owner: AuthenticatedUser = Depends(require_manager),  # noqa: B008
) -> dict[str, str]:
    user = _load_managed_member(
        request.app.state.db_path,
        user_id,
        _system_limit(request.app.state.db_path),
        owner["role"],
    )
    if user["elfie_count"] > 0:
        raise HTTPException(
            status_code=409, detail="该用户仍有名下精灵，请先处理精灵归属后再移除"
        )
    deleted = InterfaceQueryRepository(request.app.state.db_path).delete_member(user_id)
    if not deleted:
        raise HTTPException(
            status_code=409, detail="该用户仍有名下精灵，请先处理精灵归属后再移除"
        )
    logger.info("Manager removed user %s (id=%d)", user["account_id"], user_id)
    return {"detail": f"用户 {user['account_id']} 已移除"}


@router.post("/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    request: Request,
    owner: AuthenticatedUser = Depends(require_manager),  # noqa: B008
) -> dict[str, str]:
    """重置下级账号密码为随机生成的临时密码。"""
    user = _load_managed_member(
        request.app.state.db_path,
        user_id,
        _system_limit(request.app.state.db_path),
        owner["role"],
    )
    try:
        result = MemberService(request.app.state.db_path).reset_password(user_id)
    except MemberMutationTargetError as error:
        raise HTTPException(status_code=409, detail="目标账号已无法管理") from error
    logger.info(
        "Manager reset password for user %s (id=%d)", user["account_id"], user_id
    )
    return {"temporary_password": result.temporary_password}


@router.get("/{user_id}/avatar")
async def user_avatar(
    user_id: int,
    request: Request,
    owner: AuthenticatedUser = Depends(require_manager),  # noqa: B008
) -> FileResponse:
    _ = owner
    row = InterfaceQueryRepository(request.app.state.db_path).get_user(user_id)
    if row is None or not row.avatar_path:
        raise HTTPException(status_code=404, detail="用户头像不存在")
    data_home = data_home_from_db_path(request.app.state.db_path)
    candidate = (
        final_root_layout(data_home).user(str(user_id)).assets
        / Path(row.avatar_path).name
    )
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="用户头像文件不存在")
    return FileResponse(candidate, headers={"Cache-Control": "no-store"})
