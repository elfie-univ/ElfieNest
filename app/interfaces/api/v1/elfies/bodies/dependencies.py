"""Injected external-body Feature dependency."""

from fastapi import HTTPException, Request

from app.features.bodies import BodiesService


def bodies_service(request: Request) -> BodiesService:
    service = getattr(request.app.state, "bodies", None)
    if not isinstance(service, BodiesService):
        raise HTTPException(status_code=500, detail="Bodies service is not configured")
    return service


__all__ = ("bodies_service",)
