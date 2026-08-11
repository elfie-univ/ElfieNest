"""Canonical JSON error envelope for every HTTP boundary path."""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    location: tuple[str, ...]
    message: str
    kind: str


class ApiErrorDetails(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    issues: tuple[ValidationIssue, ...] = Field(default=())


class ApiErrorItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str
    details: ApiErrorDetails


class ApiErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    error: ApiErrorItem


def api_error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    issues: tuple[ValidationIssue, ...] = (),
) -> JSONResponse:
    body = ApiErrorResponse(
        error=ApiErrorItem(
            code=code,
            message=message,
            details=ApiErrorDetails(issues=issues),
        )
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def http_error_code(status_code: int) -> str:
    return {
        400: "invalid_request",
        401: "authentication_required",
        403: "request_forbidden",
        404: "resource_not_found",
        408: "request_timeout",
        413: "request_too_large",
        422: "invalid_request",
        429: "request_rate_limited",
        500: "service_not_configured",
        503: "service_unavailable",
    }.get(status_code, "request_failed")


def error_message(detail: Any) -> str:
    return detail if isinstance(detail, str) else "请求失败"


__all__ = (
    "ApiErrorDetails",
    "ApiErrorItem",
    "ApiErrorResponse",
    "ValidationIssue",
    "api_error_response",
    "error_message",
    "http_error_code",
)
