"""Versioned resource routes for the current member's Adoption journey."""

from __future__ import annotations

from typing import Literal, Union, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from app.features.accounts import AccountPrincipal
from app.features.adoption import (
    AdoptionCandidateNotAccepted,
    AdoptionCandidateSetExpired,
    AdoptionCapacityReached,
    AdoptionError,
    AdoptionInvalid,
    AdoptionNestCapacityReached,
    AdoptionOwnerNotFound,
    AdoptionService,
    AdoptionSessionBusy,
    AdoptionUnavailable,
    CandidateAppearance,
    CreateCandidateSetCommand,
    GetAdoptionOptionsQuery,
    ReplyToCandidatesCommand,
    SpeciesImageKind,
)
from app.interfaces.api.runtime_capability import (
    RuntimeCapabilityDenied,
    require_runtime_capability,
)
from app.interfaces.api.v1.auth import require_user
from app.orchestration.resident_admission import (
    AdmitAcceptedAdoptionCommand,
    ResidentAdmissionError,
    ResidentAdmissionService,
)

from .dependencies import adoption_service, resident_admission_service
from .models import (
    AdoptionCommitRequest,
    AdoptionErrorDetails,
    AdoptionErrorItem,
    AdoptionErrorResponse,
    AdoptionOptionsResponse,
    AdoptionResultResponse,
    CandidateRepliesRequest,
    CandidateRepliesResponse,
    CandidateSetRequest,
    CandidateSetResponse,
)

router = APIRouter(prefix="/api/v1/me/adoption", tags=["me-adoption"])
CurrentPrincipal = Depends(require_user)
AdoptionDependency = Depends(adoption_service)
ResidentAdmissionDependency = Depends(resident_admission_service)


@router.get("", response_model=AdoptionOptionsResponse)
def get_adoption_options(
    request: Request,
    principal: AccountPrincipal = CurrentPrincipal,
    service: AdoptionService = AdoptionDependency,
) -> Union[AdoptionOptionsResponse, JSONResponse]:
    try:
        require_runtime_capability(request.app, "adoption")
        result = service.get_options(principal, GetAdoptionOptionsQuery())
    except RuntimeCapabilityDenied as error:
        return _capability_error_response(error)
    except AdoptionError as error:
        return _error_response(error)
    return AdoptionOptionsResponse.from_result(result)


@router.post("/candidate-sets", response_model=CandidateSetResponse)
def create_candidate_set(
    body: CandidateSetRequest,
    request: Request,
    principal: AccountPrincipal = CurrentPrincipal,
    service: AdoptionService = AdoptionDependency,
) -> Union[CandidateSetResponse, JSONResponse]:
    try:
        require_runtime_capability(request.app, "adoption")
        result = service.create_candidate_set(
            principal,
            CreateCandidateSetCommand(
                species_id=body.species_id,
                life_stage=body.life_stage,
                gender=body.gender,
                appearance=CandidateAppearance(
                    stature=body.appearance.stature,
                    build=body.appearance.build,
                    face=body.appearance.face,
                    signature=body.appearance.signature,
                    priority=body.appearance.priority,
                ),
                answers=body.answers,
                adoption_session_id=body.adoption_session_id,
                batch_number=body.batch_number,
            ),
        )
    except RuntimeCapabilityDenied as error:
        return _capability_error_response(error)
    except AdoptionError as error:
        return _error_response(error)
    return CandidateSetResponse.from_result(result)


@router.get("/species/{species_id}/images/{image_kind}", response_model=None)
def get_species_image(
    species_id: str,
    image_kind: Literal["headshot", "full-body"],
    principal: AccountPrincipal = CurrentPrincipal,
    service: AdoptionService = AdoptionDependency,
) -> Union[Response, JSONResponse]:
    try:
        image = service.get_species_image(
            principal,
            species_id,
            cast(SpeciesImageKind, image_kind),
        )
    except AdoptionError as error:
        return _error_response(error)
    return Response(
        content=image.content,
        media_type=image.media_type,
        headers={
            "ETag": f'"{image.etag}"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.post(
    "/candidate-sets/{candidate_set_id}/replies",
    response_model=CandidateRepliesResponse,
)
def reply_to_candidates(
    candidate_set_id: str,
    body: CandidateRepliesRequest,
    request: Request,
    principal: AccountPrincipal = CurrentPrincipal,
    service: AdoptionService = AdoptionDependency,
) -> Union[CandidateRepliesResponse, JSONResponse]:
    try:
        require_runtime_capability(request.app, "adoption")
        result = service.reply_to_candidates(
            principal,
            ReplyToCandidatesCommand(
                candidate_set_id=candidate_set_id,
                candidate_ids=body.candidate_ids,
                invitation_message=body.invitation_message,
            ),
        )
    except RuntimeCapabilityDenied as error:
        return _capability_error_response(error)
    except AdoptionError as error:
        return _error_response(error)
    return CandidateRepliesResponse.from_result(result)


@router.post("", status_code=201, response_model=AdoptionResultResponse)
def commit_adoption(
    body: AdoptionCommitRequest,
    request: Request,
    principal: AccountPrincipal = CurrentPrincipal,
    service: ResidentAdmissionService = ResidentAdmissionDependency,
) -> Union[AdoptionResultResponse, JSONResponse]:
    try:
        require_runtime_capability(request.app, "adoption")
        result = service.admit(
            principal,
            AdmitAcceptedAdoptionCommand(
                candidate_set_id=body.candidate_set_id,
                candidate_id=body.candidate_id,
                name=body.name,
                full_body_image_url=body.full_body_image_url,
                headshot_image_url=body.headshot_image_url,
            ),
        )
    except RuntimeCapabilityDenied as error:
        return _capability_error_response(error)
    except (AdoptionError, ResidentAdmissionError) as error:
        return _error_response(error)
    return AdoptionResultResponse.from_result(result)


def _error_response(error: Exception) -> JSONResponse:
    status_code = 503
    code = "adoption_unavailable"
    details = AdoptionErrorDetails()
    if isinstance(error, AdoptionInvalid):
        status_code = 422
        code = "invalid_adoption"
    elif isinstance(error, AdoptionCandidateSetExpired):
        status_code = 410
        code = "adoption_candidate_set_expired"
    elif isinstance(error, AdoptionCandidateNotAccepted):
        status_code = 409
        code = "adoption_candidate_not_accepted"
    elif isinstance(error, AdoptionSessionBusy):
        status_code = 409
        code = "adoption_session_busy"
    elif isinstance(error, AdoptionCapacityReached):
        status_code = 409
        code = "elfie_capacity_reached"
        details = AdoptionErrorDetails(limit=error.limit)
    elif isinstance(error, AdoptionNestCapacityReached):
        status_code = 409
        code = "nest_capacity_reached"
        details = AdoptionErrorDetails(limit=error.limit)
    elif isinstance(error, AdoptionOwnerNotFound):
        status_code = 404
        code = "adoption_owner_not_found"
    elif isinstance(error, AdoptionUnavailable):
        code = "adoption_unavailable"
    elif isinstance(error, ResidentAdmissionError):
        code = "elfie_runtime_unavailable"
    payload = AdoptionErrorResponse(
        error=AdoptionErrorItem(
            code=code,
            message=str(error),
            details=details,
        )
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


def _capability_error_response(error: RuntimeCapabilityDenied) -> JSONResponse:
    payload = AdoptionErrorResponse(
        error=AdoptionErrorItem(
            code=error.code,
            message=error.detail,
            details=AdoptionErrorDetails(),
        )
    )
    return JSONResponse(status_code=503, content=payload.model_dump())


__all__ = ("router",)
