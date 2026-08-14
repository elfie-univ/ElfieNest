"""Versioned administrator HTTP boundary for global Settings."""

from __future__ import annotations

from typing import Annotated, Callable, TypeVar, Union

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.features.accounts import AccountPrincipal
from app.features.configuration import (
    ElfieSettingsResult,
    GetElfieSettingsQuery,
    GetRuntimeSettingsQuery,
    GetSecuritySettingsQuery,
    LoginRateLimit,
    SecuritySettingsResult,
    SettingsForbidden,
    SettingsService,
    SettingsStorageError,
    SettingsValidationError,
    UpdateElfieSettingsCommand,
    UpdateRuntimeSettingsCommand,
    UpdateSecuritySettingsCommand,
)
from app.interfaces.api.v1.auth import require_manager

from .models import (
    ElfieSettingsPatch,
    ElfieSettingsResponse,
    ErrorResponse,
    LoginRateLimitResponse,
    RuntimeSettingsPatch,
    RuntimeSettingsResponse,
    SecuritySettingsPatch,
    SecuritySettingsResponse,
)

router = APIRouter(
    prefix="/api/v1/admin/settings",
    tags=["admin-settings"],
)


def settings_service(request: Request) -> SettingsService:
    service = getattr(request.app.state, "settings", None)
    if not isinstance(service, SettingsService):
        raise HTTPException(status_code=503, detail="Settings service unavailable")
    return service


CurrentManager = Annotated[AccountPrincipal, Depends(require_manager)]
SettingsDependency = Annotated[SettingsService, Depends(settings_service)]
ResultT = TypeVar("ResultT")


@router.get(
    "/elfies",
    response_model=ElfieSettingsResponse,
    responses={403: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def get_elfie_settings(
    principal: CurrentManager,
    service: SettingsDependency,
) -> Union[ElfieSettingsResponse, JSONResponse]:
    result = _execute(
        lambda: service.get_elfie_settings(principal, GetElfieSettingsQuery())
    )
    if isinstance(result, JSONResponse):
        return result
    return _elfie_response(result)


@router.patch(
    "/elfies",
    response_model=ElfieSettingsResponse,
    responses={
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def update_elfie_settings(
    body: ElfieSettingsPatch,
    principal: CurrentManager,
    service: SettingsDependency,
) -> Union[ElfieSettingsResponse, JSONResponse]:
    result = _execute(
        lambda: service.update_elfie_settings(
            principal,
            UpdateElfieSettingsCommand(
                max_elfies_per_user=body.max_elfies_per_user,
                personality_presets_enabled=(
                    None
                    if body.personality_presets_enabled is None
                    else tuple(body.personality_presets_enabled.items())
                ),
            ),
        )
    )
    if isinstance(result, JSONResponse):
        return result
    return _elfie_response(result)


@router.get(
    "/runtime",
    response_model=RuntimeSettingsResponse,
    responses={403: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def get_runtime_settings(
    principal: CurrentManager,
    service: SettingsDependency,
) -> Union[RuntimeSettingsResponse, JSONResponse]:
    result = _execute(
        lambda: service.get_runtime_settings(principal, GetRuntimeSettingsQuery())
    )
    if isinstance(result, JSONResponse):
        return result
    return RuntimeSettingsResponse(tick_interval_sec=result.tick_interval_sec)


@router.patch(
    "/runtime",
    response_model=RuntimeSettingsResponse,
    responses={
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def update_runtime_settings(
    body: RuntimeSettingsPatch,
    principal: CurrentManager,
    service: SettingsDependency,
) -> Union[RuntimeSettingsResponse, JSONResponse]:
    result = _execute(
        lambda: service.update_runtime_settings(
            principal,
            UpdateRuntimeSettingsCommand(
                tick_interval_sec=(
                    None
                    if body.tick_interval_sec is None
                    else float(body.tick_interval_sec)
                )
            ),
        )
    )
    if isinstance(result, JSONResponse):
        return result
    return RuntimeSettingsResponse(tick_interval_sec=result.tick_interval_sec)


@router.get(
    "/security",
    response_model=SecuritySettingsResponse,
    responses={403: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def get_security_settings(
    principal: CurrentManager,
    service: SettingsDependency,
) -> Union[SecuritySettingsResponse, JSONResponse]:
    result = _execute(
        lambda: service.get_security_settings(principal, GetSecuritySettingsQuery())
    )
    if isinstance(result, JSONResponse):
        return result
    return _security_response(result)


@router.patch(
    "/security",
    response_model=SecuritySettingsResponse,
    responses={
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def update_security_settings(
    body: SecuritySettingsPatch,
    principal: CurrentManager,
    service: SettingsDependency,
) -> Union[SecuritySettingsResponse, JSONResponse]:
    rate_limit = None
    if body.rate_limit is not None:
        rate_limit = LoginRateLimit(
            max_attempts=body.rate_limit.max_attempts,
            window_seconds=body.rate_limit.window_seconds,
        )
    result = _execute(
        lambda: service.update_security_settings(
            principal,
            UpdateSecuritySettingsCommand(
                session_ttl_days=body.session_ttl_days,
                rate_limit=rate_limit,
            ),
        )
    )
    if isinstance(result, JSONResponse):
        return result
    return _security_response(result)


def _execute(call: Callable[[], ResultT]) -> Union[ResultT, JSONResponse]:
    try:
        return call()
    except SettingsForbidden as error:
        return _error(403, "settings_forbidden", str(error))
    except SettingsValidationError as error:
        return _error(422, "invalid_settings", str(error))
    except SettingsStorageError:
        return _error(503, "settings_unavailable", "全局设置暂时不可用")


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def _elfie_response(result: ElfieSettingsResult) -> ElfieSettingsResponse:
    return ElfieSettingsResponse(
        max_elfies_per_user=result.max_elfies_per_user,
        personality_presets_enabled=dict(result.personality_presets_enabled),
    )


def _security_response(result: SecuritySettingsResult) -> SecuritySettingsResponse:
    return SecuritySettingsResponse(
        session_ttl_days=result.session_ttl_days,
        rate_limit=LoginRateLimitResponse(
            max_attempts=result.rate_limit.max_attempts,
            window_seconds=result.rate_limit.window_seconds,
        ),
    )


__all__ = ("router", "settings_service")
