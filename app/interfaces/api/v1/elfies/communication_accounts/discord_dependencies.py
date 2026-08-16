from __future__ import annotations

from fastapi import HTTPException, Request

from app.features.communication import DiscordAccountsService


def discord_accounts_service(request: Request) -> DiscordAccountsService:
    service = getattr(request.app.state, "discord_accounts", None)
    if not isinstance(service, DiscordAccountsService):
        raise HTTPException(status_code=500, detail="Discord 服务未装配")
    return service


__all__ = ("discord_accounts_service",)
