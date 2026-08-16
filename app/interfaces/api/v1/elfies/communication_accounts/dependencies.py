from __future__ import annotations

from fastapi import HTTPException, Request

from app.features.communication import TelegramAccountsService


def telegram_accounts_service(request: Request) -> TelegramAccountsService:
    service = getattr(request.app.state, "telegram_accounts", None)
    if not isinstance(service, TelegramAccountsService):
        raise HTTPException(status_code=500, detail="Telegram 服务未装配")
    return service


__all__ = ("telegram_accounts_service",)
