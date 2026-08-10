"""Injected dependencies and restricted principals for Setup routes."""

from __future__ import annotations

from fastapi import HTTPException, Request

from app.features.setup import SetupPrincipal, SetupService
from app.interfaces.api.v1.auth import accounts_service
from app.orchestration.setup_installation import SetupInstallationService

_LOCAL_CLIENTS = frozenset({"127.0.0.1", "::1", "testclient"})


def setup_service(request: Request) -> SetupService:
    service = getattr(request.app.state, "setup", None)
    if not isinstance(service, SetupService):
        raise HTTPException(status_code=503, detail="Setup service unavailable")
    return service


def setup_installation_service(request: Request) -> SetupInstallationService:
    service = getattr(request.app.state, "setup_installation", None)
    if not isinstance(service, SetupInstallationService):
        raise HTTPException(
            status_code=503, detail="Setup installation service unavailable"
        )
    return service


def setup_principal(request: Request) -> SetupPrincipal:
    local = request.client is not None and request.client.host in _LOCAL_CLIENTS
    session_token = request.cookies.get("session_token", "")
    if session_token:
        principal = accounts_service(request).authenticate_session(session_token)
        if principal is not None and principal.role == "owner":
            return SetupPrincipal(kind="owner", local=local)
    if request.cookies.get("setup_token"):
        return SetupPrincipal(kind="setup", local=local)
    raise HTTPException(status_code=403, detail="缺少 Setup 或 Owner 凭据")


__all__ = ("setup_installation_service", "setup_principal", "setup_service")
