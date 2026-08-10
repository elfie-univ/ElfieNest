"""Injected Adoption boundaries for HTTP routes."""

from fastapi import HTTPException, Request

from app.features.adoption import AdoptionService
from app.orchestration.resident_admission import ResidentAdmissionService


def adoption_service(request: Request) -> AdoptionService:
    service = getattr(request.app.state, "adoption", None)
    if not isinstance(service, AdoptionService):
        raise HTTPException(status_code=500, detail="应用未装配领养服务")
    return service


def resident_admission_service(request: Request) -> ResidentAdmissionService:
    service = getattr(request.app.state, "resident_admission", None)
    if not isinstance(service, ResidentAdmissionService):
        raise HTTPException(status_code=500, detail="应用未装配精灵接纳服务")
    return service


__all__ = ("adoption_service", "resident_admission_service")
