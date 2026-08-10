"""Versioned administrator account-management routes."""

from __future__ import annotations

from typing import Union

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse

from app.features.accounts import (
    AccountConflict,
    AccountForbidden,
    AccountNotFound,
    AccountPrincipal,
    AccountsError,
    AccountsService,
    AccountsUnavailable,
    AccountValidationFailed,
    AvatarNotFound,
    CreateManagedAccountCommand,
    DeleteManagedAccountCommand,
    GetManagedAvatarQuery,
    ListManagedAccountsQuery,
    ManagedAccountCapacityReached,
    ManagedAccountHasElfies,
    ManagedAccountResult,
    ResetManagedAccountPasswordCommand,
    UpdateManagedAccountQuotaCommand,
)
from app.interfaces.api.v1.auth import accounts_service, require_user

from .models import (
    AdminUsersErrorDetails,
    AdminUsersErrorItem,
    AdminUsersErrorResponse,
    CreateManagedUserRequest,
    ManagedUserResponse,
    ManagedUsersResponse,
    TemporaryPasswordResponse,
    UpdateManagedUserRequest,
)

router = APIRouter(prefix="/api/v1/admin/users", tags=["admin-users"])
CurrentPrincipal = Depends(require_user)
AccountsDependency = Depends(accounts_service)


@router.get("", response_model=ManagedUsersResponse)
def list_users(
    principal: AccountPrincipal = CurrentPrincipal,
    service: AccountsService = AccountsDependency,
) -> Union[ManagedUsersResponse, JSONResponse]:
    try:
        result = service.list_managed_accounts(
            principal, ListManagedAccountsQuery()
        )
    except AccountsError as error:
        return admin_users_error_response(error)
    return ManagedUsersResponse(items=tuple(_user_response(item) for item in result.items))


@router.post("", status_code=201, response_model=ManagedUserResponse)
def create_user(
    body: CreateManagedUserRequest,
    principal: AccountPrincipal = CurrentPrincipal,
    service: AccountsService = AccountsDependency,
) -> Union[ManagedUserResponse, JSONResponse]:
    try:
        result = service.create_managed_account(
            principal,
            CreateManagedAccountCommand(
                account_id=body.account_id,
                display_name=body.display_name,
                password=body.password,
                role=body.role,
            ),
        )
    except AccountsError as error:
        return admin_users_error_response(error)
    return _user_response(result)


@router.patch("/{user_id}", response_model=ManagedUserResponse)
def update_user(
    user_id: int,
    body: UpdateManagedUserRequest,
    principal: AccountPrincipal = CurrentPrincipal,
    service: AccountsService = AccountsDependency,
) -> Union[ManagedUserResponse, JSONResponse]:
    if "elfie_quota_override" not in body.model_fields_set:
        return admin_users_error_response(
            AccountValidationFailed("必须提供 elfie_quota_override")
        )
    try:
        result = service.update_managed_quota(
            principal,
            UpdateManagedAccountQuotaCommand(
                user_id=user_id,
                elfie_quota_override=body.elfie_quota_override,
            ),
        )
    except AccountsError as error:
        return admin_users_error_response(error)
    return _user_response(result)


@router.delete(
    "/{user_id}",
    status_code=204,
    response_model=None,
    response_class=Response,
)
def delete_user(
    user_id: int,
    principal: AccountPrincipal = CurrentPrincipal,
    service: AccountsService = AccountsDependency,
) -> Union[Response, JSONResponse]:
    try:
        service.delete_managed_account(
            principal, DeleteManagedAccountCommand(user_id=user_id)
        )
    except AccountsError as error:
        return admin_users_error_response(error)
    return Response(status_code=204)


@router.post(
    "/{user_id}/reset-password",
    response_model=TemporaryPasswordResponse,
)
def reset_user_password(
    user_id: int,
    principal: AccountPrincipal = CurrentPrincipal,
    service: AccountsService = AccountsDependency,
) -> Union[TemporaryPasswordResponse, JSONResponse]:
    try:
        result = service.reset_managed_password(
            principal,
            ResetManagedAccountPasswordCommand(user_id=user_id),
        )
    except AccountsError as error:
        return admin_users_error_response(error)
    return TemporaryPasswordResponse(temporary_password=result.temporary_password)


@router.get("/{user_id}/avatar", response_model=None)
def user_avatar(
    user_id: int,
    principal: AccountPrincipal = CurrentPrincipal,
    service: AccountsService = AccountsDependency,
) -> Union[Response, JSONResponse]:
    try:
        result = service.get_managed_avatar(
            principal, GetManagedAvatarQuery(user_id=user_id)
        )
    except AccountsError as error:
        return admin_users_error_response(error)
    return Response(
        content=result.content,
        media_type=result.content_type,
        headers={"Cache-Control": "no-store"},
    )


def _user_response(result: ManagedAccountResult) -> ManagedUserResponse:
    avatar_url = (
        f"/api/v1/admin/users/{result.user_id}/avatar" if result.has_avatar else None
    )
    return ManagedUserResponse(
        user_id=result.user_id,
        account_id=result.account_id,
        display_name=result.display_name,
        role=result.role,
        gender=result.gender,
        birth_date=result.birth_date,
        presence=result.presence,
        last_seen_at=result.last_seen_at,
        language=result.language,
        created_at=result.created_at,
        elfie_count=result.elfie_count,
        elfie_quota_override=result.elfie_quota_override,
        effective_elfie_limit=result.effective_elfie_limit,
        avatar_url=avatar_url,
    )


def admin_users_error_response(error: Exception) -> JSONResponse:
    status_code = 503
    code = "accounts_unavailable"
    if isinstance(error, AccountForbidden):
        status_code = 403
        code = "account_forbidden"
    elif isinstance(error, AccountNotFound):
        status_code = 404
        code = "account_not_found"
    elif isinstance(error, AvatarNotFound):
        status_code = 404
        code = "avatar_not_found"
    elif isinstance(error, AccountConflict):
        status_code = 409
        code = "account_conflict"
    elif isinstance(error, AccountValidationFailed):
        status_code = 422
        code = "invalid_account_request"
    elif isinstance(error, ManagedAccountCapacityReached):
        status_code = 409
        code = "account_capacity_reached"
    elif isinstance(error, ManagedAccountHasElfies):
        status_code = 409
        code = "account_has_elfies"
    elif not isinstance(error, AccountsUnavailable):
        error = AccountsUnavailable("账户服务暂时不可用")
    payload = AdminUsersErrorResponse(
        error=AdminUsersErrorItem(
            code=code,
            message=str(error),
            details=AdminUsersErrorDetails(),
        )
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


__all__ = ("admin_users_error_response", "router")
