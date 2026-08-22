"""Versioned routes for member-visible Elfie projections."""

from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse, Response

from app.features.accounts import AccountPrincipal
from app.features.elfies import (
    ElfieNotFound,
    ElfiePortraitInvalid,
    ElfiePortraitTooLarge,
    ElfiesError,
    ElfiesForbidden,
    ElfiesService,
    ElfiesUnavailable,
    GetElfiePortraitQuery,
    GetElfieProfileQuery,
    ListVisibleElfiesQuery,
    UpdateElfiePortraitCommand,
)
from app.interfaces.api.v1.auth import require_user

from .dependencies import elfies_service
from .models import (
    ElfiePortraitUploadResponse,
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
_MAX_PORTRAIT_BYTES = 2 * 1024 * 1024
_PORTRAIT_READ_CHUNK_BYTES = 64 * 1024


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


@router.get("/{elfie_id}/portrait", response_class=Response)
def get_elfie_portrait(
    elfie_id: str,
    kind: Literal["headshot", "full_body"] = Query(default="headshot"),
    principal: AccountPrincipal = CurrentPrincipal,
    service: ElfiesService = ElfiesDependency,
) -> Response:
    try:
        result = service.get_portrait(
            principal,
            GetElfiePortraitQuery(elfie_id=elfie_id, kind=kind),
        )
    except (ElfieNotFound, ElfiesUnavailable) as error:
        return elfies_error_response(error)
    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={"Cache-Control": "no-store"},
    )


@router.put("/{elfie_id}/portrait", response_model=ElfiePortraitUploadResponse)
async def update_elfie_portrait(
    elfie_id: str,
    file: Annotated[UploadFile, File()],
    principal: AccountPrincipal = CurrentPrincipal,
    service: ElfiesService = ElfiesDependency,
) -> Union[ElfiePortraitUploadResponse, JSONResponse]:
    try:
        content = await _read_portrait_limited(file)
        service.update_portrait(
            principal,
            UpdateElfiePortraitCommand(
                elfie_id=elfie_id,
                content_type=file.content_type or "",
                content=content,
            ),
        )
    except ElfiesError as error:
        return elfies_error_response(error)
    return ElfiePortraitUploadResponse(
        portrait_url=f"/api/v1/elfies/{elfie_id}/portrait"
    )


async def _read_portrait_limited(file: UploadFile) -> bytes:
    image = bytearray()
    while len(image) <= _MAX_PORTRAIT_BYTES:
        chunk = await file.read(
            min(
                _PORTRAIT_READ_CHUNK_BYTES,
                _MAX_PORTRAIT_BYTES + 1 - len(image),
            )
        )
        if not chunk:
            break
        image.extend(chunk)
    if len(image) > _MAX_PORTRAIT_BYTES:
        raise ElfiePortraitTooLarge("Elfie portrait exceeds 2 MiB")
    return bytes(image)


def elfies_error_response(error: Exception) -> JSONResponse:
    status_code = 503
    code = "elfies_unavailable"
    if isinstance(error, ElfieNotFound):
        status_code = 404
        code = "elfie_not_found"
    elif isinstance(error, ElfiesForbidden):
        status_code = 403
        code = "elfies_forbidden"
    elif isinstance(error, ElfiePortraitTooLarge):
        status_code = 413
        code = "elfie_portrait_too_large"
    elif isinstance(error, ElfiePortraitInvalid):
        status_code = 415
        code = "invalid_elfie_portrait"
    payload = ElfiesErrorResponse(
        error=ElfiesErrorItem(
            code=code,
            message=str(error),
            details=ElfiesErrorDetails(),
        )
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


__all__ = ("elfies_error_response", "router")
