"""Injected Elfies query dependency for HTTP routes."""

from fastapi import HTTPException, Request

from app.features.elfies import ElfiesService


def elfies_service(request: Request) -> ElfiesService:
    service = getattr(request.app.state, "elfies", None)
    if not isinstance(service, ElfiesService):
        raise HTTPException(status_code=500, detail="应用未装配 Elfies 查询服务")
    return service


__all__ = ("elfies_service",)
