"""Versioned administrator boundary for existing Embodiment sessions."""

from __future__ import annotations

from typing import Union

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.features.accounts import AccountPrincipal
from app.interfaces.api.v1.auth import require_user
from app.orchestration.embodiment import (
    EmbodimentError,
    EmbodimentForbidden,
    EmbodimentSessionService,
    EmbodimentUnavailable,
    ListEmbodimentSessionsQuery,
)

from .models import (
    EmbodimentSessionResponse,
    EmbodimentSessionsErrorDetails,
    EmbodimentSessionsErrorItem,
    EmbodimentSessionsErrorResponse,
    EmbodimentSessionsResponse,
)

router = APIRouter(
    prefix="/api/v1/admin/runtime/embodiment-sessions",
    tags=["admin-runtime"],
)
CurrentPrincipal = Depends(require_user)


def embodiment_service(request: Request) -> EmbodimentSessionService:
    service = getattr(request.app.state, "embodiment", None)
    if not isinstance(service, EmbodimentSessionService):
        raise EmbodimentUnavailable("Embodiment sessions unavailable")
    return service


@router.get(
    "",
    response_model=EmbodimentSessionsResponse,
    responses={
        403: {"model": EmbodimentSessionsErrorResponse},
        503: {"model": EmbodimentSessionsErrorResponse},
    },
)
def list_embodiment_sessions(
    request: Request,
    principal: AccountPrincipal = CurrentPrincipal,
) -> Union[EmbodimentSessionsResponse, JSONResponse]:
    try:
        service = embodiment_service(request)
        sessions = service.list_sessions(principal, ListEmbodimentSessionsQuery())
    except EmbodimentError as error:
        return _error_response(error)
    return EmbodimentSessionsResponse(
        items=tuple(
            EmbodimentSessionResponse(
                elfie_id=session.elfie_id,
                state=session.state.value,
                body_id=session.body_id,
            )
            for session in sessions
        )
    )


def _error_response(error: EmbodimentError) -> JSONResponse:
    status_code = 503
    code = "embodiment_sessions_unavailable"
    if isinstance(error, EmbodimentForbidden):
        status_code = 403
        code = "embodiment_sessions_forbidden"
    body = EmbodimentSessionsErrorResponse(
        error=EmbodimentSessionsErrorItem(
            code=code,
            message=str(error),
            details=EmbodimentSessionsErrorDetails(),
        )
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


__all__ = ("embodiment_service", "router")
