"""Injected Providers dependency for versioned HTTP routes."""

from fastapi import HTTPException, Request

from app.features.configuration import ProviderAvailabilityPort, ProvidersService


def providers_service(request: Request) -> ProvidersService:
    service = getattr(request.app.state, "providers", None)
    if not isinstance(service, ProvidersService):
        raise HTTPException(status_code=500, detail="应用未装配 Provider 管理服务")
    return service


def provider_availability(request: Request) -> ProviderAvailabilityPort:
    service = getattr(request.app.state, "provider_availability", None)
    if service is None:
        raise HTTPException(status_code=500, detail="应用未装配 Provider 可用性查询")
    return service


__all__ = ("provider_availability", "providers_service")
