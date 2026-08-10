"""Versioned administrator HTTP boundary for Runtime status."""

from __future__ import annotations

from typing import Union

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.features.accounts import AccountPrincipal
from app.features.operations import (
    GetRuntimeStatusQuery,
    OperationsError,
    OperationsFacade,
    OperationsForbidden,
    OperationsUnavailable,
    RuntimeEventResult,
)
from app.interfaces.api.v1.auth import require_user

from .models import (
    RuntimeErrorDetails,
    RuntimeErrorItem,
    RuntimeErrorResponse,
    RuntimeEventResponse,
    RuntimeObserverResponse,
    RuntimeStatusResponse,
)

router = APIRouter(prefix="/api/v1/admin/runtime", tags=["admin-runtime"])
CurrentPrincipal = Depends(require_user)


def operations_facade(request: Request) -> OperationsFacade:
    facade = getattr(request.app.state, "operations", None)
    if not isinstance(facade, OperationsFacade):
        raise OperationsUnavailable("Operations service unavailable")
    return facade


@router.get(
    "/status",
    response_model=RuntimeStatusResponse,
    responses={
        403: {"model": RuntimeErrorResponse},
        503: {"model": RuntimeErrorResponse},
    },
)
def get_runtime_status(
    request: Request,
    principal: AccountPrincipal = CurrentPrincipal,
) -> Union[RuntimeStatusResponse, JSONResponse]:
    try:
        operations = operations_facade(request)
        result = operations.get_runtime_status(principal, GetRuntimeStatusQuery())
    except OperationsError as error:
        return runtime_error_response(error)
    last_event = (
        None
        if result.observer.last_event is None
        else _event_response(result.observer.last_event)
    )
    return RuntimeStatusResponse(
        status=result.status,
        observer=RuntimeObserverResponse(
            event_count=result.observer.event_count,
            last_event=last_event,
        ),
    )


def runtime_error_response(error: OperationsError) -> JSONResponse:
    status_code = 503
    code = "runtime_status_unavailable"
    message = "运行状态暂时不可用"
    if isinstance(error, OperationsForbidden):
        status_code = 403
        code = "runtime_status_forbidden"
        message = str(error)
    elif not isinstance(error, OperationsUnavailable):
        code = "runtime_status_failed"
    body = RuntimeErrorResponse(
        error=RuntimeErrorItem(
            code=code,
            message=message,
            details=RuntimeErrorDetails(),
        )
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def _event_response(event: RuntimeEventResult) -> RuntimeEventResponse:
    return RuntimeEventResponse(
        event_type=event.event_type,
        status=event.status,
        subject=event.subject,
        metadata={item.key: item.value for item in event.metadata},
    )


__all__ = ("operations_facade", "router", "runtime_error_response")
