"""Injected Nest Management dependency for HTTP routes."""

from fastapi import HTTPException, Request

from app.features.nest_management import NestManagementService


def nest_management_service(request: Request) -> NestManagementService:
    service = getattr(request.app.state, "nest_management", None)
    if not isinstance(service, NestManagementService):
        raise HTTPException(status_code=500, detail="应用未装配 Nest 管理服务")
    return service


__all__ = ("nest_management_service",)
