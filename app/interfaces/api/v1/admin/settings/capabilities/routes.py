"""Versioned administrator routes for global capability settings."""

from __future__ import annotations

from typing import Annotated, FrozenSet, Union

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.features.accounts import AccountPrincipal
from app.features.configuration import (
    CapabilitiesForbidden,
    CapabilitiesService,
    CapabilitiesUnavailable,
    CapabilitiesValidationError,
    CapabilityKey,
    ListCapabilitiesQuery,
    LocalFileUpdateField,
    UpdateLocalFileCapabilityCommand,
    UpdateWebSearchCapabilityCommand,
    VerifyCapabilityCommand,
    WebSearchUpdateField,
)
from app.interfaces.api.v1.auth import require_user

from .dependencies import capabilities_service
from .models import (
    CapabilitiesResponse,
    CapabilityConfigurationResponse,
    CapabilityErrorDetails,
    CapabilityErrorItem,
    CapabilityErrorResponse,
    CapabilityValidationSuiteResponse,
    LocalFileCapabilityPatch,
    LocalFileCapabilityResponse,
    LocalFileCapabilityUpdateResponse,
    WebSearchCapabilityPatch,
    WebSearchCapabilityResponse,
    WebSearchCapabilityUpdateResponse,
)
from .validation import CapabilityAPIRoute

router = APIRouter(
    prefix="/api/v1/admin/settings/capabilities",
    tags=["admin-capabilities"],
    route_class=CapabilityAPIRoute,
)
CurrentPrincipal = Annotated[AccountPrincipal, Depends(require_user)]
CapabilitiesDependency = Annotated[CapabilitiesService, Depends(capabilities_service)]


@router.get(
    "",
    response_model=CapabilitiesResponse,
    responses={
        403: {"model": CapabilityErrorResponse},
        503: {"model": CapabilityErrorResponse},
    },
)
def list_capabilities(
    principal: CurrentPrincipal,
    service: CapabilitiesDependency,
) -> Union[CapabilitiesResponse, JSONResponse]:
    try:
        result = service.list_capabilities(principal, ListCapabilitiesQuery())
    except (CapabilitiesForbidden, CapabilitiesUnavailable) as error:
        return _error_response(error)
    return CapabilitiesResponse(
        tools=CapabilityConfigurationResponse(
            web_search=WebSearchCapabilityResponse.from_result(result.web_search),
            local_file=LocalFileCapabilityResponse.from_result(result.local_file),
        )
    )


@router.patch(
    "/web-search",
    response_model=WebSearchCapabilityUpdateResponse,
    responses={
        403: {"model": CapabilityErrorResponse},
        422: {"model": CapabilityErrorResponse},
        503: {"model": CapabilityErrorResponse},
    },
)
def update_web_search(
    body: WebSearchCapabilityPatch,
    principal: CurrentPrincipal,
    service: CapabilitiesDependency,
) -> Union[WebSearchCapabilityUpdateResponse, JSONResponse]:
    fields = _web_search_fields(body.model_fields_set)
    try:
        result = service.update_web_search(
            principal,
            UpdateWebSearchCapabilityCommand(
                fields=fields,
                enabled=body.enabled,
                provider=body.provider,
                api_base=body.api_base,
                api_key=(body.api_key if "api_key" in body.model_fields_set else None),
                max_results=body.max_results,
                max_result_bytes=body.max_result_bytes,
            ),
        )
    except (
        CapabilitiesForbidden,
        CapabilitiesUnavailable,
        CapabilitiesValidationError,
    ) as error:
        return _error_response(error)
    return WebSearchCapabilityUpdateResponse(
        tool_key="web_search",
        config=WebSearchCapabilityResponse.from_result(result),
    )


@router.patch(
    "/local-file",
    response_model=LocalFileCapabilityUpdateResponse,
    responses={
        403: {"model": CapabilityErrorResponse},
        422: {"model": CapabilityErrorResponse},
        503: {"model": CapabilityErrorResponse},
    },
)
def update_local_file(
    body: LocalFileCapabilityPatch,
    principal: CurrentPrincipal,
    service: CapabilitiesDependency,
) -> Union[LocalFileCapabilityUpdateResponse, JSONResponse]:
    try:
        result = service.update_local_file(
            principal,
            UpdateLocalFileCapabilityCommand(
                fields=_local_file_fields(body.model_fields_set),
                enabled=body.enabled,
                max_read_bytes=body.max_read_bytes,
            ),
        )
    except (
        CapabilitiesForbidden,
        CapabilitiesUnavailable,
        CapabilitiesValidationError,
    ) as error:
        return _error_response(error)
    return LocalFileCapabilityUpdateResponse(
        tool_key="local_file",
        config=LocalFileCapabilityResponse.from_result(result),
    )


@router.post(
    "/web-search/verify",
    response_model=CapabilityValidationSuiteResponse,
    responses={
        403: {"model": CapabilityErrorResponse},
        503: {"model": CapabilityErrorResponse},
    },
)
def verify_web_search(
    principal: CurrentPrincipal,
    service: CapabilitiesDependency,
) -> Union[CapabilityValidationSuiteResponse, JSONResponse]:
    return _verify("web_search", principal, service)


@router.post(
    "/local-file/verify",
    response_model=CapabilityValidationSuiteResponse,
    responses={
        403: {"model": CapabilityErrorResponse},
        503: {"model": CapabilityErrorResponse},
    },
)
def verify_local_file(
    principal: CurrentPrincipal,
    service: CapabilitiesDependency,
) -> Union[CapabilityValidationSuiteResponse, JSONResponse]:
    return _verify("local_file", principal, service)


def _verify(
    capability_key: CapabilityKey,
    principal: AccountPrincipal,
    service: CapabilitiesService,
) -> Union[CapabilityValidationSuiteResponse, JSONResponse]:
    try:
        result = service.verify_capability(
            principal, VerifyCapabilityCommand(capability_key=capability_key)
        )
    except (CapabilitiesForbidden, CapabilitiesUnavailable) as error:
        return _error_response(error)
    return CapabilityValidationSuiteResponse.from_result(result)


def _web_search_fields(fields: set[str]) -> FrozenSet[WebSearchUpdateField]:
    result: set[WebSearchUpdateField] = set()
    if "enabled" in fields:
        result.add("enabled")
    if "provider" in fields:
        result.add("provider")
    if "api_base" in fields:
        result.add("api_base")
    if "max_results" in fields:
        result.add("max_results")
    if "max_result_bytes" in fields:
        result.add("max_result_bytes")
    return frozenset(result)


def _local_file_fields(fields: set[str]) -> FrozenSet[LocalFileUpdateField]:
    result: set[LocalFileUpdateField] = set()
    if "enabled" in fields:
        result.add("enabled")
    if "max_read_bytes" in fields:
        result.add("max_read_bytes")
    return frozenset(result)


def _error_response(error: Exception) -> JSONResponse:
    status_code = 503
    code = "capabilities_unavailable"
    message = "系统能力配置暂时不可用"
    if isinstance(error, CapabilitiesForbidden):
        status_code = 403
        code = "capabilities_forbidden"
        message = str(error)
    elif isinstance(error, CapabilitiesValidationError):
        status_code = 422
        code = "invalid_capability_configuration"
        message = str(error)
    payload = CapabilityErrorResponse(
        error=CapabilityErrorItem(
            code=code,
            message=message,
            details=CapabilityErrorDetails(),
        )
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


__all__ = ("router",)
