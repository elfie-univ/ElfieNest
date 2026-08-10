"""Versioned routes for administrator Elfie projections."""

from __future__ import annotations

from typing import Optional, Union

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.features.accounts import AccountPrincipal
from app.features.elfies import (
    ElfiesForbidden,
    ElfiesService,
    ElfiesUnavailable,
    ListAdminElfiesQuery,
)
from app.interfaces.api.v1.auth import require_user
from app.interfaces.api.v1.elfies.dependencies import elfies_service
from app.interfaces.api.v1.elfies.models import (
    ElfiesErrorDetails,
    ElfiesErrorItem,
    ElfiesErrorResponse,
)

from .models import AdminElfieResponse, AdminElfiesResponse

router = APIRouter(prefix="/api/v1/admin/elfies", tags=["admin-elfies"])
CurrentPrincipal = Depends(require_user)
ElfiesDependency = Depends(elfies_service)


@router.get("", response_model=AdminElfiesResponse)
def list_admin_elfies(
    owner_user_id: Optional[int] = Query(default=None, gt=0),
    species_id: Optional[str] = Query(default=None, min_length=1),
    principal: AccountPrincipal = CurrentPrincipal,
    service: ElfiesService = ElfiesDependency,
) -> Union[AdminElfiesResponse, JSONResponse]:
    try:
        results = service.list_admin(
            principal,
            ListAdminElfiesQuery(
                owner_user_id=owner_user_id,
                species_id=species_id,
            ),
        )
    except (ElfiesForbidden, ElfiesUnavailable) as error:
        return _error_response(error)
    return AdminElfiesResponse(
        items=tuple(AdminElfieResponse.model_validate(item) for item in results)
    )


def _error_response(error: Exception) -> JSONResponse:
    status_code = 503
    code = "elfies_unavailable"
    if isinstance(error, ElfiesForbidden):
        status_code = 403
        code = "elfies_forbidden"
    payload = ElfiesErrorResponse(
        error=ElfiesErrorItem(
            code=code,
            message=str(error),
            details=ElfiesErrorDetails(),
        )
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


__all__ = ("router",)
