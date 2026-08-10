"""Injected Providers dependency for versioned HTTP routes."""

from fastapi import HTTPException, Request

from app.features.configuration import ProvidersService


def providers_service(request: Request) -> ProvidersService:
    service = getattr(request.app.state, "providers", None)
    if not isinstance(service, ProvidersService):
        raise HTTPException(status_code=500, detail="应用未装配 Provider 管理服务")
    return service


__all__ = ("providers_service",)
