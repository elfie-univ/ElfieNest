"""Versioned current-account self-service routes."""

from __future__ import annotations

from typing import Annotated, Final, Union

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from app.features.accounts import (
    AccountConflict,
    AccountForbidden,
    AccountNotFound,
    AccountPrincipal,
    AccountProfileResult,
    AccountsError,
    AccountsService,
    AccountsUnavailable,
    AccountValidationFailed,
    AvatarContentInvalid,
    AvatarMediaTypeUnsupported,
    AvatarNotFound,
    AvatarTooLarge,
    ChangePasswordCommand,
    CurrentPasswordIncorrect,
    GetAvatarQuery,
    GetCurrentAccountQuery,
    InvalidAvatar,
    PasswordReuseRejected,
    ProfileField,
    UpdateAccountProfileCommand,
    UpdateLandingPageCommand,
    UpdateThemeCommand,
    UploadAvatarCommand,
)
from app.interfaces.api.v1.auth import (
    accounts_service,
    generate_csrf_token,
    require_user,
)

from .models import (
    AccountsErrorDetails,
    AccountsErrorItem,
    AccountsErrorResponse,
    AvatarUploadResponse,
    CurrentAccountResponse,
    DetailResponse,
    LandingPageRequest,
    LandingPageResponse,
    PasswordChangeRequest,
    ProfileResponse,
    ProfileUpdateRequest,
    ThemePreferenceRequest,
    ThemePreferenceResponse,
)

router = APIRouter(prefix="/api/v1/me", tags=["me"])
CurrentPrincipal = Depends(require_user)
AccountsDependency = Depends(accounts_service)
_MAX_AVATAR_BYTES: Final = 2 * 1024 * 1024
_AVATAR_URL: Final = "/api/v1/me/avatar"


@router.get("", response_model=CurrentAccountResponse)
def current_account(
    request: Request,
    principal: AccountPrincipal = CurrentPrincipal,
    service: AccountsService = AccountsDependency,
) -> Union[CurrentAccountResponse, JSONResponse]:
    try:
        result = service.get_current_account(principal, GetCurrentAccountQuery())
    except AccountsError as error:
        return accounts_error_response(error)
    return _current_response(
        result,
        generate_csrf_token(request.cookies.get("session_token", "")),
    )


@router.patch("/profile", response_model=ProfileResponse)
def update_profile(
    body: ProfileUpdateRequest,
    principal: AccountPrincipal = CurrentPrincipal,
    service: AccountsService = AccountsDependency,
) -> Union[ProfileResponse, JSONResponse]:
    try:
        result = service.update_profile(
            principal,
            UpdateAccountProfileCommand(
                fields=_profile_fields(body),
                account_id=body.account_id,
                display_name=body.display_name,
                gender=body.gender,
                birth_date=(
                    None if body.birth_date is None else body.birth_date.isoformat()
                ),
                avatar_color=body.avatar_color,
                avatar_kind=body.avatar_kind,
            ),
        )
    except AccountsError as error:
        return accounts_error_response(error)
    return _profile_response(result)


@router.post("/password", response_model=DetailResponse)
def change_password(
    body: PasswordChangeRequest,
    request: Request,
    principal: AccountPrincipal = CurrentPrincipal,
    service: AccountsService = AccountsDependency,
) -> Union[DetailResponse, JSONResponse]:
    try:
        service.change_password(
            principal,
            ChangePasswordCommand(
                old_password=body.old_password,
                new_password=body.new_password,
                current_session_token=request.cookies.get("session_token", ""),
            ),
        )
    except AccountsError as error:
        return accounts_error_response(error)
    return DetailResponse(detail="密码已更新")


@router.put("/theme", response_model=ThemePreferenceResponse)
def update_theme(
    body: ThemePreferenceRequest,
    principal: AccountPrincipal = CurrentPrincipal,
    service: AccountsService = AccountsDependency,
) -> Union[ThemePreferenceResponse, JSONResponse]:
    try:
        service.update_theme(principal, UpdateThemeCommand(theme_key=body.theme_key))
    except AccountsError as error:
        return accounts_error_response(error)
    return ThemePreferenceResponse(theme_key=body.theme_key)


@router.put("/default-landing-page", response_model=LandingPageResponse)
def update_default_landing_page(
    body: LandingPageRequest,
    principal: AccountPrincipal = CurrentPrincipal,
    service: AccountsService = AccountsDependency,
) -> Union[LandingPageResponse, JSONResponse]:
    try:
        service.update_default_landing_page(
            principal,
            UpdateLandingPageCommand(default_landing_page=body.default_landing_page),
        )
    except AccountsError as error:
        return accounts_error_response(error)
    return LandingPageResponse(default_landing_page=body.default_landing_page)


@router.post("/avatar", status_code=201, response_model=AvatarUploadResponse)
async def upload_avatar(
    file: Annotated[UploadFile, File()],
    principal: AccountPrincipal = CurrentPrincipal,
    service: AccountsService = AccountsDependency,
) -> Union[AvatarUploadResponse, JSONResponse]:
    content = await _read_avatar_limited(file)
    try:
        service.upload_avatar(
            principal,
            UploadAvatarCommand(
                content_type=file.content_type or "",
                content=content,
            ),
        )
    except AccountsError as error:
        return accounts_error_response(error)
    return AvatarUploadResponse(avatar_url=_AVATAR_URL)


@router.get("/avatar", response_model=None)
def current_avatar(
    principal: AccountPrincipal = CurrentPrincipal,
    service: AccountsService = AccountsDependency,
) -> Union[Response, JSONResponse]:
    try:
        result = service.get_avatar(principal, GetAvatarQuery())
    except AccountsError as error:
        return accounts_error_response(error)
    return Response(
        content=result.content,
        media_type=result.content_type,
        headers={"Cache-Control": "no-store"},
    )


async def _read_avatar_limited(file: UploadFile) -> bytes:
    image = bytearray()
    while len(image) <= _MAX_AVATAR_BYTES:
        chunk = await file.read(_MAX_AVATAR_BYTES + 1 - len(image))
        if not chunk:
            break
        image.extend(chunk)
    return bytes(image)


def _profile_fields(body: ProfileUpdateRequest) -> frozenset[ProfileField]:
    fields: list[ProfileField] = []
    if "account_id" in body.model_fields_set:
        fields.append("account_id")
    if "display_name" in body.model_fields_set:
        fields.append("display_name")
    if "gender" in body.model_fields_set:
        fields.append("gender")
    if "birth_date" in body.model_fields_set:
        fields.append("birth_date")
    if "avatar_color" in body.model_fields_set:
        fields.append("avatar_color")
    if "avatar_kind" in body.model_fields_set:
        fields.append("avatar_kind")
    return frozenset(fields)


def _current_response(
    result: AccountProfileResult, csrf_token: str
) -> CurrentAccountResponse:
    return CurrentAccountResponse(
        user_id=result.user_id,
        account_id=result.account_id,
        display_name=result.display_name,
        gender=result.gender,
        birth_date=result.birth_date,
        role=result.role,
        avatar_url=_AVATAR_URL if result.has_avatar else None,
        avatar_color=result.avatar_color,
        avatar_kind=result.avatar_kind,
        theme_key=result.theme_key,
        default_landing_page=result.default_landing_page,
        created_at=result.created_at,
        elfie_count=result.elfie_count,
        csrf_token=csrf_token,
    )


def _profile_response(result: AccountProfileResult) -> ProfileResponse:
    return ProfileResponse(
        user_id=result.user_id,
        account_id=result.account_id,
        display_name=result.display_name,
        gender=result.gender,
        birth_date=result.birth_date,
        avatar_url=_AVATAR_URL if result.has_avatar else None,
        avatar_color=result.avatar_color,
        avatar_kind=result.avatar_kind,
    )


def accounts_error_response(error: Exception) -> JSONResponse:
    status_code = 503
    code = "accounts_unavailable"
    if isinstance(error, AccountForbidden):
        status_code = 403
        code = "account_forbidden"
    elif isinstance(error, AccountNotFound):
        status_code = 404
        code = "account_not_found"
    elif isinstance(error, AccountConflict):
        status_code = 409
        code = "account_conflict"
    elif isinstance(error, AvatarTooLarge):
        status_code = 413
        code = "avatar_too_large"
    elif isinstance(error, AvatarMediaTypeUnsupported):
        status_code = 415
        code = "unsupported_avatar_media_type"
    elif isinstance(error, AvatarContentInvalid):
        status_code = 415
        code = "invalid_avatar_content"
    elif isinstance(error, (AccountValidationFailed, InvalidAvatar)):
        status_code = 422
        code = "invalid_account_request"
    elif isinstance(error, CurrentPasswordIncorrect):
        status_code = 400
        code = "current_password_incorrect"
    elif isinstance(error, PasswordReuseRejected):
        status_code = 400
        code = "password_reuse_rejected"
    elif isinstance(error, AvatarNotFound):
        status_code = 404
        code = "avatar_not_found"
    elif not isinstance(error, AccountsUnavailable):
        message = "账户服务暂时不可用"
        payload = AccountsErrorResponse(
            error=AccountsErrorItem(
                code=code,
                message=message,
                details=AccountsErrorDetails(),
            )
        )
        return JSONResponse(status_code=status_code, content=payload.model_dump())
    payload = AccountsErrorResponse(
        error=AccountsErrorItem(
            code=code,
            message=str(error),
            details=AccountsErrorDetails(),
        )
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


__all__ = ("accounts_error_response", "router")
