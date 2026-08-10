"""Versioned external-body resources belonging to one Elfie."""

from __future__ import annotations

from typing import Union

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse

from app.features.accounts import AccountPrincipal
from app.features.bodies import (
    BodiesError,
    BodiesForbidden,
    BodiesService,
    BodiesUnavailable,
    BodyConflict,
    BodyInputInvalid,
    BodyNotFound,
    EnrollBodyCommand,
    ListBodiesQuery,
    RevokeBodyCommand,
    RotateBodyCredentialCommand,
)
from app.interfaces.api.v1.auth import require_user

from .dependencies import bodies_service
from .models import (
    BodiesResponse,
    BodyCredentialResponse,
    BodyEnrollmentRequest,
    BodyErrorDetails,
    BodyErrorItem,
    BodyErrorResponse,
    BodyResponse,
)

router = APIRouter(prefix="/api/v1/elfies", tags=["elfie-bodies"])
CurrentPrincipal = Depends(require_user)
BodiesDependency = Depends(bodies_service)


@router.get("/{elfie_id}/bodies", response_model=BodiesResponse)
def list_bodies(
    elfie_id: str,
    principal: AccountPrincipal = CurrentPrincipal,
    service: BodiesService = BodiesDependency,
) -> Union[BodiesResponse, JSONResponse]:
    try:
        items = service.list_bodies(principal, ListBodiesQuery(elfie_id=elfie_id))
    except BodiesError as error:
        return _error_response(error)
    return BodiesResponse(items=tuple(BodyResponse.from_result(item) for item in items))


@router.post(
    "/{elfie_id}/bodies",
    response_model=BodyCredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
def enroll_body(
    elfie_id: str,
    body: BodyEnrollmentRequest,
    principal: AccountPrincipal = CurrentPrincipal,
    service: BodiesService = BodiesDependency,
) -> Union[BodyCredentialResponse, JSONResponse]:
    try:
        result = service.enroll_body(
            principal,
            EnrollBodyCommand(
                elfie_id=elfie_id,
                display_name=body.display_name,
                body_type=body.body_type,
            ),
        )
    except BodiesError as error:
        return _error_response(error)
    return BodyCredentialResponse.from_result(result)


@router.post(
    "/{elfie_id}/bodies/{body_id}/credential-rotations",
    response_model=BodyCredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
def rotate_body_credential(
    elfie_id: str,
    body_id: str,
    principal: AccountPrincipal = CurrentPrincipal,
    service: BodiesService = BodiesDependency,
) -> Union[BodyCredentialResponse, JSONResponse]:
    try:
        result = service.rotate_credential(
            principal,
            RotateBodyCredentialCommand(elfie_id=elfie_id, body_id=body_id),
        )
    except BodiesError as error:
        return _error_response(error)
    return BodyCredentialResponse.from_result(result)


@router.delete(
    "/{elfie_id}/bodies/{body_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def revoke_body(
    elfie_id: str,
    body_id: str,
    principal: AccountPrincipal = CurrentPrincipal,
    service: BodiesService = BodiesDependency,
) -> Union[Response, JSONResponse]:
    try:
        service.revoke_body(
            principal,
            RevokeBodyCommand(elfie_id=elfie_id, body_id=body_id),
        )
    except BodiesError as error:
        return _error_response(error)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _error_response(error: BodiesError) -> JSONResponse:
    status_code = 503
    code = "bodies_unavailable"
    if isinstance(error, BodiesForbidden):
        status_code = 403
        code = "bodies_forbidden"
    elif isinstance(error, BodyInputInvalid):
        status_code = 422
        code = "invalid_body_request"
    elif isinstance(error, BodyNotFound):
        status_code = 404
        code = "body_not_found"
    elif isinstance(error, BodyConflict):
        status_code = 409
        code = "body_conflict"
    elif isinstance(error, BodiesUnavailable):
        status_code = 503
    payload = BodyErrorResponse(
        error=BodyErrorItem(
            code=code,
            message=str(error),
            details=BodyErrorDetails(),
        )
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


__all__ = ("router",)
