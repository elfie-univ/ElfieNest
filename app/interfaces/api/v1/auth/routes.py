"""Versioned login and logout routes."""

from __future__ import annotations

from typing import Union

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.features.accounts import (
    AccountPrincipal,
    AccountsService,
    AuthenticationFailed,
    LoginCommand,
    LoginRateLimited,
)
from app.orchestration.observer import ObserverFacade, session_token_fingerprint

from ...page_routes import post_login_landing_path
from .dependencies import accounts_service, get_current_user
from .models import AuthUserResponse, ErrorResponse, LoginResponse, LogoutResponse
from .security import generate_csrf_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
AccountsDependency = Depends(accounts_service)
CurrentPrincipal = Depends(get_current_user)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    responses={
        401: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
)
async def login(
    request: Request,
    service: AccountsService = AccountsDependency,
) -> Union[LoginResponse, JSONResponse]:
    body = await request.form()
    if "username" in body:
        return _error(422, "invalid_login_request", "不支持旧账号字段 username")
    account_id_raw = body.get("account_id")
    password_raw = body.get("password")
    account_id = account_id_raw.strip() if isinstance(account_id_raw, str) else ""
    password = password_raw if isinstance(password_raw, str) else ""
    if not account_id or not password:
        return _error(422, "invalid_login_request", "登录账号和密码不能为空")
    client_key = request.client.host if request.client else "unknown"
    try:
        authenticated = service.login(
            LoginCommand(
                account_id=account_id,
                password=password,
                client_key=client_key,
            )
        )
    except LoginRateLimited:
        return _error(429, "login_rate_limited", "登录尝试过于频繁，请稍后再试")
    except AuthenticationFailed:
        return _error(401, "authentication_failed", "登录账号或密码错误")

    csrf_token = generate_csrf_token(authenticated.session_token)
    principal = authenticated.principal
    response_body = LoginResponse(
        user=AuthUserResponse(
            user_id=principal.user_id,
            account_id=principal.account_id,
            display_name=authenticated.display_name,
            role=principal.role,
            default_landing_page=principal.default_landing_page,
        ),
        csrf_token=csrf_token,
        landing_path=post_login_landing_path(
            principal, request.query_params.get("next")
        ),
    )
    response = JSONResponse(content=response_body.model_dump(mode="json"))
    response.set_cookie(
        key="session_token",
        value=authenticated.session_token,
        httponly=True,
        samesite="lax",
        max_age=authenticated.ttl_seconds,
    )
    response.headers["X-CSRF-Token"] = csrf_token
    return response


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    request: Request,
    principal: AccountPrincipal = CurrentPrincipal,
    service: AccountsService = AccountsDependency,
) -> JSONResponse:
    _ = principal
    token = request.cookies.get("session_token", "")
    if token:
        observer = getattr(request.app.state, "observer", None)
        if isinstance(observer, ObserverFacade):
            observer.revoke_session(session_token_fingerprint(token))
        service.logout(token)
    response = JSONResponse(content={"detail": "已登出"})
    response.delete_cookie(key="session_token")
    return response


__all__ = ("router",)
