"""Versioned routes for member-visible Elfie projections."""

from __future__ import annotations

from typing import Literal, Optional, Union

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.features.accounts import AccountPrincipal
from app.features.elfies import (
    ElfieNotFound,
    ElfiesService,
    ElfiesUnavailable,
    GetElfieProfileQuery,
    ListVisibleElfiesQuery,
)
from app.interfaces.api.v1.auth import require_user

from .dependencies import elfies_service
from .models import (
    ElfieProfileDetailResponse,
    ElfiesErrorDetails,
    ElfiesErrorItem,
    ElfiesErrorResponse,
    VisibleElfieResponse,
    VisibleElfiesResponse,
)

router = APIRouter(prefix="/api/v1/elfies", tags=["elfies"])
CurrentPrincipal = Depends(require_user)
ElfiesDependency = Depends(elfies_service)


@router.get("", response_model=VisibleElfiesResponse)
def list_visible_elfies(
    relationship: Optional[Literal["owned"]] = None,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ElfiesService = ElfiesDependency,
) -> Union[VisibleElfiesResponse, JSONResponse]:
    try:
        results = service.list_visible(
            principal,
            ListVisibleElfiesQuery(relationship=relationship),
        )
    except ElfiesUnavailable as error:
        return elfies_error_response(error)
    return VisibleElfiesResponse(
        items=tuple(VisibleElfieResponse.model_validate(item) for item in results)
    )


@router.get("/{elfie_id}/profile", response_model=ElfieProfileDetailResponse)
def get_elfie_profile(
    elfie_id: str,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ElfiesService = ElfiesDependency,
) -> Union[ElfieProfileDetailResponse, JSONResponse]:
    try:
        result = service.get_profile(
            principal,
            GetElfieProfileQuery(elfie_id=elfie_id),
        )
    except (ElfieNotFound, ElfiesUnavailable) as error:
        return elfies_error_response(error)
    return ElfieProfileDetailResponse.model_validate(result)


def elfies_error_response(error: Exception) -> JSONResponse:
    status_code = 503
    code = "elfies_unavailable"
    if isinstance(error, ElfieNotFound):
        status_code = 404
        code = "elfie_not_found"
    payload = ElfiesErrorResponse(
        error=ElfiesErrorItem(
            code=code,
            message=str(error),
            details=ElfiesErrorDetails(),
        )
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


__all__ = ("elfies_error_response", "router")
