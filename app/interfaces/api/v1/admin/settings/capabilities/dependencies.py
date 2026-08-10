"""Injected Capabilities dependency for versioned HTTP routes."""

from __future__ import annotations

from fastapi import HTTPException, Request

from app.features.configuration import CapabilitiesService


def capabilities_service(request: Request) -> CapabilitiesService:
    service = getattr(request.app.state, "capabilities", None)
    if not isinstance(service, CapabilitiesService):
        raise HTTPException(status_code=503, detail="Capabilities service unavailable")
    return service


__all__ = ("capabilities_service",)
