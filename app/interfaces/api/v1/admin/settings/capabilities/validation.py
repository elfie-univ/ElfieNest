"""Capability-local validation error normalization."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute

from .models import (
    CapabilityErrorDetails,
    CapabilityErrorItem,
    CapabilityErrorResponse,
)


class CapabilityAPIRoute(APIRoute):
    """Keep request validation on the standard product error envelope."""

    def get_route_handler(  # type: ignore[override]
        self,
    ) -> Callable[[Request], Awaitable[Response]]:
        original = super().get_route_handler()

        async def validated(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError:
                payload = CapabilityErrorResponse(
                    error=CapabilityErrorItem(
                        code="invalid_capability_configuration",
                        message="能力配置请求无效",
                        details=CapabilityErrorDetails(),
                    )
                )
                return JSONResponse(
                    status_code=422,
                    content=payload.model_dump(),
                )

        return validated


__all__ = ("CapabilityAPIRoute",)
