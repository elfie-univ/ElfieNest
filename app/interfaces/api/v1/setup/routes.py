"""Strict versioned first-run Setup resources."""

from __future__ import annotations

import secrets
from typing import Annotated, Union

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
    SetupUnavailable,
    SetupValidationError,
)
from app.interfaces.api.v1.auth import generate_csrf_token
from app.orchestration.setup_installation import (
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


@router.get("/status", response_model=SetupStatusResponse)
def get_status(
    request: Request, service: SetupDependency
) -> Union[SetupStatusResponse, JSONResponse]:
    try:
        result = service.get_status(GetSetupStatusQuery())
    except SetupUnavailable as error:
        return _error(error)
    source = request.cookies.get("setup_token") or request.cookies.get("session_token")
    if result.need_setup and source is None:
        source = secrets.token_hex(32)
        csrf = generate_csrf_token(source)
        response = JSONResponse(
            content=SetupStatusResponse.from_result(result, csrf_token=csrf).model_dump(
                mode="json"
            )
        )
        response.set_cookie(
            "setup_token",
            source,
            httponly=True,
            samesite="strict",
            max_age=900,
            path="/",
        )
        response.headers["X-CSRF-Token"] = csrf
        return response
    return SetupStatusResponse.from_result(
        result, csrf_token=generate_csrf_token(source) if source else None
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
    return SetupStatusResponse.from_result(result)


@router.put("/draft/offline", response_model=SetupStatusResponse)
def save_offline(
    body: SetupOfflineDraftRequest,
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
    return SetupStatusResponse.from_result(result)


@router.put("/draft/nest", response_model=SetupStatusResponse)
def save_nest(
    body: SetupNestDraftRequest,
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
    return SetupStatusResponse.from_result(result)


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
    return JSONResponse(status_code=status, content=payload.model_dump())


__all__ = ("router",)
