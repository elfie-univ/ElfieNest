"""Setup-local request validation normalization."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute

from .models import SetupErrorDetails, SetupErrorItem, SetupErrorResponse


class SetupAPIRoute(APIRoute):
    def get_route_handler(  # type: ignore[override]
        self,
    ) -> Callable[[Request], Awaitable[Response]]:
        original = super().get_route_handler()

        async def validated(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError:
                payload = SetupErrorResponse(
                    error=SetupErrorItem(
                        code="invalid_setup",
                        message="Setup 请求无效",
                        details=SetupErrorDetails(),
                    )
                )
                return JSONResponse(status_code=422, content=payload.model_dump())
            except HTTPException as error:
                message = str(error.detail)
                payload = SetupErrorResponse(
                    error=SetupErrorItem(
                        code=(
                            "setup_forbidden"
                            if error.status_code in {401, 403}
                            else "setup_unavailable"
                        ),
                        message=message,
                        details=SetupErrorDetails(),
                    )
                )
                return JSONResponse(
                    status_code=error.status_code,
                    content=payload.model_dump(),
                )

        return validated


__all__ = ("SetupAPIRoute",)
