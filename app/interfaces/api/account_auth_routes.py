"""Canonical account authentication and self-service profile routes."""

from __future__ import annotations

from datetime import date
from typing import Dict, Final, Literal, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.features.accounts import (
    AccountPrincipal,
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.infrastructure.persistence.account_repository import (
    AccountConflictError,
    AccountValidationError,
)
from app.infrastructure.persistence.runtime_query_repository import (
    RuntimeAccount,
    RuntimeQueryRepository,
)

from .profile_routes import avatar_url
from .v1.auth import generate_csrf_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["account"])
CurrentUser = Depends(get_current_user)
_MODEL_CONFIG: Final[ConfigDict] = ConfigDict(extra="forbid", frozen=True)


class ProfileUpdate(BaseModel):
    model_config = _MODEL_CONFIG

    account_id: Optional[str] = Field(None, min_length=3, max_length=32)
    display_name: Optional[str] = Field(None, max_length=64)
    gender: Optional[Literal["male", "female"]] = None
    birth_date: Optional[date] = None
    avatar_color: Optional[int] = Field(None, ge=0, le=7)
    avatar_kind: Optional[str] = Field(None, pattern="^(initials|emoji)$")


class PasswordChange(BaseModel):
    model_config = _MODEL_CONFIG

    old_password: str
    new_password: str = Field(..., min_length=6, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        """Require six effective characters after trimming outer whitespace."""
        return validate_password_strength(value)


class ThemePreferenceUpdate(BaseModel):
    model_config = _MODEL_CONFIG

    theme_key: str = Field(
        ...,
        pattern="^(warm-paper|harbor-blue|orchid-archive|moss-green)$",
    )


def _account_profile(account: RuntimeAccount) -> Dict[str, Union[str, int, None]]:
    return {
        "user_id": account.user_id,
        "account_id": account.account_id,
        "display_name": account.display_name,
        "gender": account.gender,
        "birth_date": account.birth_date,
        "avatar_color": account.avatar_color,
        "avatar_kind": account.avatar_kind,
        "avatar_url": avatar_url(account.avatar_path),
    }


@router.get("/me")
async def me(
    request: Request,
    user: AccountPrincipal = CurrentUser,
) -> Dict[str, Union[str, int, None]]:
    """Return the canonical current-account and profile projection."""
    repository = RuntimeQueryRepository(request.app.state.db_path)
    account = repository.find_account_by_id(user.user_id)
    if account is None:
        raise HTTPException(status_code=401, detail="账户不存在")
    result = _account_profile(account)
    result.update(
        {
            "role": account.role,
            "default_landing_page": account.default_landing_page,
            "theme_key": account.theme_key,
            "created_at": account.created_at,
            "elfie_count": len(repository.list_elfies_for_owner(account.user_id)),
            "csrf_token": generate_csrf_token(request.cookies.get("session_token", "")),
        }
    )
    return result


@router.put("/me/profile")
async def update_profile(
    body: ProfileUpdate,
    request: Request,
    user: AccountPrincipal = CurrentUser,
) -> Dict[str, Union[str, int, None]]:
    """Update display name and the existing avatar presentation fields."""
    if not body.model_fields_set:
        raise HTTPException(status_code=400, detail="没有提供要更新的字段")
    repository = RuntimeQueryRepository(request.app.state.db_path)
    current = repository.find_account_by_id(user.user_id)
    if current is None:
        raise HTTPException(status_code=401, detail="账户不存在")
    if "account_id" in body.model_fields_set and body.account_id is None:
        raise HTTPException(status_code=422, detail="登录账号不能为空")
    if "gender" in body.model_fields_set and body.gender is None:
        raise HTTPException(status_code=422, detail="性别只能是男或女")
    account_id = current.account_id
    display_name = current.display_name
    gender = current.gender or "male"
    birth_date = current.birth_date
    if "account_id" in body.model_fields_set and body.account_id is not None:
        account_id = body.account_id
    if "display_name" in body.model_fields_set:
        display_name = (
            None if body.display_name is None else body.display_name.strip() or None
        )
    if "gender" in body.model_fields_set and body.gender is not None:
        gender = body.gender
    if "birth_date" in body.model_fields_set:
        birth_date = None if body.birth_date is None else body.birth_date.isoformat()
    try:
        account = repository.update_profile(
            current.user_id,
            account_id=account_id,
            display_name=display_name,
            avatar_color=(
                body.avatar_color
                if body.avatar_color is not None
                else current.avatar_color
            ),
            avatar_kind=body.avatar_kind or current.avatar_kind,
            gender=gender,
            birth_date=birth_date,
        )
    except AccountValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except AccountConflictError as error:
        raise HTTPException(status_code=409, detail="登录账号已存在") from error
    if account is None:
        raise HTTPException(status_code=401, detail="账户不存在")
    return _account_profile(account)


@router.post("/me/password")
async def change_password(
    body: PasswordChange,
    request: Request,
    user: AccountPrincipal = CurrentUser,
) -> dict[str, str]:
    repository = RuntimeQueryRepository(request.app.state.db_path)
    account = repository.find_account_by_id(user.user_id)
    if account is None:
        raise HTTPException(status_code=401, detail="账户不存在")
    if not verify_password(body.old_password, account.password_hash):
        raise HTTPException(status_code=400, detail="旧密码错误")
    if body.old_password == body.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与旧密码相同")
    repository.update_password_and_revoke_other_sessions(
        account.user_id,
        hash_password(body.new_password),
        request.cookies.get("session_token", ""),
    )
    return {"detail": "密码已更新"}


@router.put("/me/theme")
async def update_theme_preference(
    body: ThemePreferenceUpdate,
    request: Request,
    user: AccountPrincipal = CurrentUser,
) -> dict[str, str]:
    RuntimeQueryRepository(request.app.state.db_path).update_theme(
        user.user_id, body.theme_key
    )
    return {"theme_key": body.theme_key}
