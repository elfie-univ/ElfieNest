"""Versioned administrator HTTP boundary for Runtime status."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Union

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.features.accounts import AccountPrincipal
from app.features.operations import (
    GetMobileAccessQuery,
    GetRuntimeStatusQuery,
    ModelExecutionEventResult,
    OperationsError,
    OperationsFacade,
    OperationsForbidden,
    OperationsUnavailable,
)
from app.interfaces.api.service_access import MobileAccessProjection
from app.interfaces.api.v1.auth import require_manager, require_user

from .models import (
    MobileAccessResponse,
    ModelExecutionEventResponse,
    ModelExecutionObserverResponse,
    RuntimeErrorDetails,
    RuntimeErrorItem,
    RuntimeErrorResponse,
    RuntimeLifecycleProjectionResponse,
    RuntimeStatusResponse,
)

router = APIRouter(prefix="/api/v1/admin/runtime", tags=["admin-runtime"])
CurrentPrincipal = Depends(require_user)
ManagerPrincipal = Depends(require_manager)


def operations_facade(request: Request) -> OperationsFacade:
    facade = getattr(request.app.state, "operations", None)
    if not isinstance(facade, OperationsFacade):
        raise OperationsUnavailable("Operations service unavailable")
    return facade


@router.get(
    "/status",
    response_model=RuntimeStatusResponse,
    response_model_exclude_none=True,
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
        observer=ModelExecutionObserverResponse(
            event_count=result.observer.event_count,
            last_event=last_event,
        ),
        lifecycle=_lifecycle_projection(request),
    )


def _lifecycle_projection(
    request: Request,
) -> RuntimeLifecycleProjectionResponse | None:
    """Read the injected authoritative projection without starting or repairing."""
    provider = getattr(request.app.state, "runtime_projection", None)
    if not callable(provider):
        return None
    try:
        payload = provider()
    except (OSError, RuntimeError, ValueError):
        return None
    if not isinstance(payload, Mapping):
        return None
    try:
        return RuntimeLifecycleProjectionResponse.model_validate(payload)
    except ValueError:
        return None


@router.get(
    "/mobile-access",
    response_model=MobileAccessResponse,
    responses={503: {"model": RuntimeErrorResponse}},
)
def get_mobile_access(
    request: Request,
    principal: AccountPrincipal = ManagerPrincipal,
) -> Union[MobileAccessResponse, JSONResponse]:
    """Return reachable LAN roots from the active Core bind policy."""
    _ = principal
    projection = getattr(request.app.state, "mobile_access", None)
    if not isinstance(projection, MobileAccessProjection):
        body = RuntimeErrorResponse(
            error=RuntimeErrorItem(
                code="mobile_access_unavailable",
                message="移动访问地址暂不可用",
                details=RuntimeErrorDetails(),
            )
        )
        return JSONResponse(status_code=503, content=body.model_dump(mode="json"))
    urls = projection.mobile_access_urls
    network_name = None
    operations = getattr(request.app.state, "operations", None)
    if isinstance(operations, OperationsFacade):
        try:
            network_name = operations.get_mobile_access(
                GetMobileAccessQuery(http_port=projection.http_port)
            ).network_name
        except OperationsError:
            pass
    return MobileAccessResponse(
        available=bool(urls),
        network_name=network_name,
        urls=urls,
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


def _event_response(event: ModelExecutionEventResult) -> ModelExecutionEventResponse:
    return ModelExecutionEventResponse(
        event_type=event.event_type,
        status=event.status,
        subject=event.subject,
        metadata={item.key: item.value for item in event.metadata},
    )


__all__ = ("operations_facade", "router", "runtime_error_response")
