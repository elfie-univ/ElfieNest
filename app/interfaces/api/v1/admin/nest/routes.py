"""Versioned administrator routes for semantic Nest management."""

from __future__ import annotations

from typing import Union

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.features.accounts import AccountPrincipal
from app.features.nest_management import (
    AssignNestHomeCommand,
    NestBedConflict,
    NestBedNotFound,
    NestConfigurationConflict,
    NestConfigurationInvalid,
    NestManagementForbidden,
    NestManagementService,
    NestManagementUnavailable,
    NestResidentNotFound,
    UpdateNestBedCountCommand,
)
from app.interfaces.api.v1.auth import require_user

from .dependencies import nest_management_service
from .models import (
    NestBedAssignmentRequest,
    NestBedAssignmentResponse,
    NestBedCountRequest,
    NestConfigurationResponse,
    NestErrorDetails,
    NestErrorItem,
    NestErrorResponse,
    NestRoomResponse,
    NestRoomsResponse,
)

router = APIRouter(prefix="/api/v1/admin/nest", tags=["admin-nest"])
CurrentPrincipal = Depends(require_user)
NestManagementDependency = Depends(nest_management_service)


@router.get("/rooms", response_model=NestRoomsResponse)
def get_rooms(
    principal: AccountPrincipal = CurrentPrincipal,
    service: NestManagementService = NestManagementDependency,
) -> Union[NestRoomsResponse, JSONResponse]:
    try:
        rooms = service.get_rooms(principal)
    except (NestManagementForbidden, NestManagementUnavailable) as error:
        return _error_response(error)
    return NestRoomsResponse(
        items=tuple(NestRoomResponse.from_result(room) for room in rooms)
    )


@router.put(
    "/rooms/default/bed-count",
    response_model=NestConfigurationResponse,
)
def update_default_room_bed_count(
    body: NestBedCountRequest,
    principal: AccountPrincipal = CurrentPrincipal,
    service: NestManagementService = NestManagementDependency,
) -> Union[NestConfigurationResponse, JSONResponse]:
    try:
        result = service.update_bed_count(
            principal,
            UpdateNestBedCountCommand(bed_count=body.bed_count),
        )
    except (
        NestConfigurationConflict,
        NestConfigurationInvalid,
        NestManagementForbidden,
        NestManagementUnavailable,
    ) as error:
        return _error_response(error)
    return NestConfigurationResponse.from_result(result)


@router.put(
    "/elfies/{elfie_id}/bed",
    response_model=NestBedAssignmentResponse,
)
def assign_bed(
    elfie_id: str,
    body: NestBedAssignmentRequest,
    principal: AccountPrincipal = CurrentPrincipal,
    service: NestManagementService = NestManagementDependency,
) -> Union[NestBedAssignmentResponse, JSONResponse]:
    try:
        result = service.assign_home(
            principal,
            AssignNestHomeCommand(
                elfie_id=elfie_id,
                home_anchor_id=body.home_anchor_id,
            ),
        )
    except (
        NestBedConflict,
        NestBedNotFound,
        NestManagementForbidden,
        NestManagementUnavailable,
        NestResidentNotFound,
    ) as error:
        return _error_response(error)
    return NestBedAssignmentResponse.from_result(result)


def _error_response(error: Exception) -> JSONResponse:
    status_code = 503
    code = "nest_management_unavailable"
    if isinstance(error, NestManagementForbidden):
        status_code = 403
        code = "nest_management_forbidden"
    elif isinstance(error, NestConfigurationInvalid):
        status_code = 422
        code = "invalid_nest_configuration"
    elif isinstance(error, NestConfigurationConflict):
        status_code = 409
        code = "nest_capacity_conflict"
    elif isinstance(error, NestResidentNotFound):
        status_code = 404
        code = "nest_resident_not_found"
    elif isinstance(error, NestBedNotFound):
        status_code = 404
        code = "nest_bed_not_found"
    elif isinstance(error, NestBedConflict):
        status_code = 409
        code = "nest_bed_conflict"
    payload = NestErrorResponse(
        error=NestErrorItem(
            code=code,
            message=str(error),
            details=NestErrorDetails(),
        )
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


__all__ = ("router",)
