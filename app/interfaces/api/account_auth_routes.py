"""Canonical account authentication and self-service profile routes."""

from __future__ import annotations

from typing import Dict, Final, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.features.accounts.auth import (
    AuthenticatedUser,
    create_session,
    delete_session,
    generate_csrf_token,
    get_current_user,
    get_rate_limiter,
    get_session_ttl_seconds,
    hash_password,
    verify_password,
)
from app.features.accounts.password_policy import validate_password_strength
from app.infrastructure.persistence.runtime_query_repository import (
    RuntimeAccount,
    RuntimeQueryRepository,
)

from .page_routes import post_login_landing_path
from .profile_routes import avatar_url

router = APIRouter(prefix="/api/auth", tags=["account"])
CurrentUser = Depends(get_current_user)
_MODEL_CONFIG: Final[ConfigDict] = ConfigDict(extra="forbid", frozen=True)


class ProfileUpdate(BaseModel):
    model_config = _MODEL_CONFIG

    display_name: Optional[str] = Field(None, max_length=64)
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
        "avatar_color": account.avatar_color,
        "avatar_kind": account.avatar_kind,
        "avatar_url": avatar_url(account.avatar_path),
    }


@router.post("/login")
async def login(request: Request) -> JSONResponse:
    """Authenticate an exact account identifier and issue the existing cookie/CSRF pair."""
    body = await request.form()
    account_id_raw = body.get("account_id")
    password_raw = body.get("password")
    if "username" in body:
        raise HTTPException(status_code=422, detail="不支持旧账号字段 username")
    account_id = account_id_raw.strip() if isinstance(account_id_raw, str) else ""
    password = password_raw if isinstance(password_raw, str) else ""
    if not account_id or not password:
        raise HTTPException(status_code=422, detail="登录账号和密码不能为空")

    client_ip = request.client.host if request.client else "unknown"
    db_path = request.app.state.db_path
    limiter = get_rate_limiter(db_path)
    if limiter.is_limited(client_ip, account_id):
        raise HTTPException(status_code=429, detail="登录尝试过于频繁，请稍后再试")

    account = RuntimeQueryRepository(db_path).find_account_by_account_id(account_id)
    if account is None or not verify_password(password, account.password_hash):
        limiter.record_failure(client_ip, account_id)
        raise HTTPException(status_code=401, detail="登录账号或密码错误")

    limiter.clear(client_ip, account_id)
    session_token = create_session(account.user_id, db_path)
    csrf_token = generate_csrf_token(session_token)
    user_data = {
        "user_id": account.user_id,
        "account_id": account.account_id,
        "display_name": account.display_name,
        "role": account.role,
        "default_landing_page": account.default_landing_page,
    }
    response = JSONResponse(
        content={
            "user": user_data,
            "csrf_token": csrf_token,
            "landing_path": post_login_landing_path(
                user_data, request.query_params.get("next")
            ),
        }
    )
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=get_session_ttl_seconds(db_path),
    )
    response.headers["X-CSRF-Token"] = csrf_token
    return response


@router.post("/logout")
async def logout(
    request: Request,
    user: AuthenticatedUser = CurrentUser,
) -> JSONResponse:
    """Revoke the authenticated session and clear its cookie."""
    _ = user
    token = request.cookies.get("session_token", "")
    if token:
        from .observer_routes import session_token_fingerprint  # noqa: PLC0415

        observer_sessions = getattr(request.app.state, "observer_sessions", None)
        if observer_sessions is not None:
            observer_sessions.revoke_session(session_token_fingerprint(token))
        delete_session(token, request.app.state.db_path)
    response = JSONResponse(content={"detail": "已登出"})
    response.delete_cookie(key="session_token")
    return response


@router.get("/me")
async def me(
    request: Request,
    user: AuthenticatedUser = CurrentUser,
) -> Dict[str, Union[str, int, None]]:
    """Return the canonical current-account and profile projection."""
    repository = RuntimeQueryRepository(request.app.state.db_path)
    account = repository.find_account_by_id(user["user_id"])
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


@router.get("/me/profile")
async def get_profile(
    request: Request,
    user: AuthenticatedUser = CurrentUser,
) -> Dict[str, Union[str, int, None]]:
    account = RuntimeQueryRepository(request.app.state.db_path).find_account_by_id(
        user["user_id"]
    )
    if account is None:
        raise HTTPException(status_code=401, detail="账户不存在")
    return _account_profile(account)


@router.put("/me/profile")
async def update_profile(
    body: ProfileUpdate,
    request: Request,
    user: AuthenticatedUser = CurrentUser,
) -> Dict[str, Union[str, int, None]]:
    """Update display name and the existing avatar presentation fields."""
    if (
        body.display_name is None
        and body.avatar_color is None
        and body.avatar_kind is None
    ):
        raise HTTPException(status_code=400, detail="没有提供要更新的字段")
    repository = RuntimeQueryRepository(request.app.state.db_path)
    current = repository.find_account_by_id(user["user_id"])
    if current is None:
        raise HTTPException(status_code=401, detail="账户不存在")
    display_name = current.display_name
    if body.display_name is not None:
        display_name = body.display_name.strip() or None
    account = repository.update_profile(
        current.user_id,
        display_name=display_name,
        avatar_color=(
            body.avatar_color if body.avatar_color is not None else current.avatar_color
        ),
        avatar_kind=body.avatar_kind or current.avatar_kind,
    )
    if account is None:
        raise HTTPException(status_code=401, detail="账户不存在")
    return _account_profile(account)


@router.post("/me/password")
async def change_password(
    body: PasswordChange,
    request: Request,
    user: AuthenticatedUser = CurrentUser,
) -> dict[str, str]:
    repository = RuntimeQueryRepository(request.app.state.db_path)
    account = repository.find_account_by_id(user["user_id"])
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
    user: AuthenticatedUser = CurrentUser,
) -> dict[str, str]:
    RuntimeQueryRepository(request.app.state.db_path).update_theme(
        user["user_id"], body.theme_key
    )
    return {"theme_key": body.theme_key}
