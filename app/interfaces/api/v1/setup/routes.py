"""Strict versioned first-run Setup resources."""

from __future__ import annotations

import secrets
from typing import Annotated, Final, Union

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.features.setup import (
    GetSetupStatusQuery,
    InspectSetupOllamaQuery,
    ListSetupModelsQuery,
    SaveSetupNestDraftCommand,
    SaveSetupOfflineDraftCommand,
    SaveSetupOwnerDraftCommand,
    SetupConflict,
    SetupForbidden,
    SetupPrincipal,
    SetupService,
    SetupStatusResult,
    SetupUnavailable,
    SetupValidationError,
)
from app.interfaces.api.v1.auth import generate_csrf_token
from app.orchestration.setup_installation import (
    CancelSetupInstallationCommand,
    ConfirmSetupInstallationCommand,
    SetupInstallationConflict,
    SetupInstallationForbidden,
    SetupInstallationInvalid,
    SetupInstallationService,
    SetupInstallationUnavailable,
)

from .dependencies import setup_installation_service, setup_principal, setup_service
from .models import (
    SetupErrorDetails,
    SetupErrorItem,
    SetupErrorResponse,
    SetupInstallationRequest,
    SetupModelCollectionResponse,
    SetupModelOptionResponse,
    SetupNestDraftRequest,
    SetupOfflineDraftRequest,
    SetupOllamaResponse,
    SetupOwnerDraftRequest,
    SetupStatusResponse,
)
from .validation import SetupAPIRoute

router = APIRouter(
    prefix="/api/v1/setup",
    tags=["setup"],
    route_class=SetupAPIRoute,
)
SetupDependency = Annotated[SetupService, Depends(setup_service)]
InstallationDependency = Annotated[
    SetupInstallationService, Depends(setup_installation_service)
]
PrincipalDependency = Annotated[SetupPrincipal, Depends(setup_principal)]

SETUP_TOKEN_MAX_AGE: Final[int] = 900
_NO_STORE_CACHE_CONTROL: Final[str] = "no-store, no-cache, must-revalidate, max-age=0"


@router.get("/status", response_model=SetupStatusResponse)
def get_status(
    request: Request, service: SetupDependency
) -> Union[SetupStatusResponse, JSONResponse]:
    try:
        result = service.get_status(GetSetupStatusQuery())
    except SetupUnavailable as error:
        return _error(error)
    setup_token = request.cookies.get("setup_token")
    if result.need_setup and not setup_token:
        setup_source = secrets.token_hex(32)
        return _status_response(
            result,
            source=setup_source,
            setup_token=setup_source,
        )
    return _status_response(
        result,
        source=setup_token or request.cookies.get("session_token"),
        setup_token=setup_token if result.need_setup else None,
    )


@router.get("/models", response_model=SetupModelCollectionResponse)
def list_models(
    service: SetupDependency,
) -> Union[SetupModelCollectionResponse, JSONResponse]:
    try:
        return SetupModelCollectionResponse(
            items=tuple(
                SetupModelOptionResponse.from_result(item)
                for item in service.list_models(ListSetupModelsQuery())
            )
        )
    except SetupUnavailable as error:
        return _error(error)


@router.put("/draft/owner", response_model=SetupStatusResponse)
def save_owner(
    body: SetupOwnerDraftRequest,
    request: Request,
    principal: PrincipalDependency,
    service: SetupDependency,
) -> Union[SetupStatusResponse, JSONResponse]:
    try:
        result = service.save_owner_draft(
            principal,
            SaveSetupOwnerDraftCommand(
                body.account_id, body.display_name, body.password
            ),
        )
    except (
        SetupConflict,
        SetupForbidden,
        SetupUnavailable,
        SetupValidationError,
    ) as error:
        return _error(error)
    return _status_response_for_request(request, result)


@router.put("/draft/offline", response_model=SetupStatusResponse)
def save_offline(
    body: SetupOfflineDraftRequest,
    request: Request,
    principal: PrincipalDependency,
    service: SetupDependency,
) -> Union[SetupStatusResponse, JSONResponse]:
    try:
        result = service.save_offline_draft(
            principal,
            SaveSetupOfflineDraftCommand(body.use_local_ollama, body.model_id),
        )
    except (
        SetupConflict,
        SetupForbidden,
        SetupUnavailable,
        SetupValidationError,
    ) as error:
        return _error(error)
    return _status_response_for_request(request, result)


@router.put("/draft/nest", response_model=SetupStatusResponse)
def save_nest(
    body: SetupNestDraftRequest,
    request: Request,
    principal: PrincipalDependency,
    service: SetupDependency,
) -> Union[SetupStatusResponse, JSONResponse]:
    try:
        result = service.save_nest_draft(
            principal, SaveSetupNestDraftCommand(body.bed_count)
        )
    except (
        SetupConflict,
        SetupForbidden,
        SetupUnavailable,
        SetupValidationError,
    ) as error:
        return _error(error)
    return _status_response_for_request(request, result)


@router.post("/installation", response_model=SetupStatusResponse, status_code=202)
def start_installation(
    body: SetupInstallationRequest,
    request: Request,
    principal: PrincipalDependency,
    service: SetupDependency,
    workflow: InstallationDependency,
) -> Union[SetupStatusResponse, JSONResponse]:
    try:
        result = workflow.confirm(
            ConfirmSetupInstallationCommand(
                principal=principal, confirmed=body.confirmed
            )
        )
        status = service.get_status(GetSetupStatusQuery())
    except (
        SetupInstallationConflict,
        SetupInstallationForbidden,
        SetupInstallationInvalid,
        SetupInstallationUnavailable,
    ) as error:
        return _error(error)
    csrf = generate_csrf_token(result.session_token)
    response = JSONResponse(
        content=SetupStatusResponse.from_result(status, csrf_token=csrf).model_dump(
            mode="json"
        ),
        status_code=200 if result.installation.task_status == "completed" else 202,
    )
    response.headers["Cache-Control"] = _NO_STORE_CACHE_CONTROL
    response.set_cookie(
        "session_token",
        result.session_token,
        httponly=True,
        samesite="lax",
        max_age=result.session_ttl_seconds,
    )
    response.delete_cookie("setup_token", path="/")
    response.headers["X-CSRF-Token"] = csrf
    return response


@router.post("/installation/cancel", response_model=SetupStatusResponse)
def cancel_installation(
    request: Request,
    principal: PrincipalDependency,
    service: SetupDependency,
    workflow: InstallationDependency,
) -> Union[SetupStatusResponse, JSONResponse]:
    try:
        workflow.cancel(CancelSetupInstallationCommand(principal=principal))
        return _status_response_for_request(
            request, service.get_status(GetSetupStatusQuery())
        )
    except (
        SetupInstallationConflict,
        SetupInstallationForbidden,
        SetupInstallationInvalid,
        SetupInstallationUnavailable,
    ) as error:
        return _error(error)


@router.get("/ollama", response_model=SetupOllamaResponse)
def inspect_ollama(
    principal: PrincipalDependency, service: SetupDependency
) -> Union[SetupOllamaResponse, JSONResponse]:
    try:
        return SetupOllamaResponse.from_result(
            service.inspect_ollama(principal, InspectSetupOllamaQuery())
        )
    except (SetupForbidden, SetupUnavailable) as error:
        return _error(error)


def _error(error: Exception) -> JSONResponse:
    status = 503
    code = "setup_unavailable"
    if isinstance(error, (SetupForbidden, SetupInstallationForbidden)):
        status, code = 403, "setup_forbidden"
    elif isinstance(error, (SetupConflict, SetupInstallationConflict)):
        status, code = 409, "setup_conflict"
    elif isinstance(error, (SetupValidationError, SetupInstallationInvalid)):
        status, code = 422, "invalid_setup"
    payload = SetupErrorResponse(
        error=SetupErrorItem(code=code, message=str(error), details=SetupErrorDetails())
    )
    response = JSONResponse(status_code=status, content=payload.model_dump())
    response.headers["Cache-Control"] = _NO_STORE_CACHE_CONTROL
    return response


def _status_response_for_request(
    request: Request, result: SetupStatusResult
) -> JSONResponse:
    setup_token = request.cookies.get("setup_token")
    return _status_response(
        result,
        source=setup_token or request.cookies.get("session_token"),
        setup_token=setup_token,
    )


def _status_response(
    result: SetupStatusResult,
    *,
    source: str | None,
    setup_token: str | None = None,
    status_code: int = 200,
) -> JSONResponse:
    csrf = generate_csrf_token(source) if source else None
    response = JSONResponse(
        content=SetupStatusResponse.from_result(result, csrf_token=csrf).model_dump(
            mode="json"
        ),
        status_code=status_code,
    )
    response.headers["Cache-Control"] = _NO_STORE_CACHE_CONTROL
    if csrf is not None:
        response.headers["X-CSRF-Token"] = csrf
    if setup_token:
        response.set_cookie(
            "setup_token",
            setup_token,
            httponly=True,
            samesite="strict",
            max_age=SETUP_TOKEN_MAX_AGE,
            path="/",
        )
    return response


__all__ = ("router",)
