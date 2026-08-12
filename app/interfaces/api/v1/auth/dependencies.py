"""FastAPI authentication dependencies backed by the injected Accounts facade."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from app.features.accounts import AccountForbidden, AccountPrincipal, AccountsService


def accounts_service(request: Request) -> AccountsService:
    service = getattr(request.app.state, "accounts", None)
    if not isinstance(service, AccountsService):
        raise HTTPException(status_code=500, detail="应用未装配账户服务")
    return service


def get_current_user(request: Request) -> AccountPrincipal:
    token = request.cookies.get("session_token", "")
    if not token:
        raise HTTPException(status_code=401, detail="未登录，缺少会话 token")
    principal = accounts_service(request).authenticate_session(token)
    if principal is None:
        raise HTTPException(status_code=401, detail="会话无效或已过期")
    return principal


CurrentPrincipal = Depends(get_current_user)
AccountsDependency = Depends(accounts_service)


def require_user(
    principal: AccountPrincipal = CurrentPrincipal,
) -> AccountPrincipal:
    return principal


def require_owner(
    principal: AccountPrincipal = CurrentPrincipal,
    service: AccountsService = AccountsDependency,
) -> AccountPrincipal:
    try:
        return service.require_owner(principal)
    except AccountForbidden as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


def require_manager(
    principal: AccountPrincipal = CurrentPrincipal,
    service: AccountsService = AccountsDependency,
) -> AccountPrincipal:
    try:
        return service.require_manager(principal)
    except AccountForbidden as error:
        raise HTTPException(status_code=403, detail=str(error)) from error


__all__ = (
    "accounts_service",
    "get_current_user",
    "require_manager",
    "require_owner",
    "require_user",
)
