"""Versioned owner routes for one Elfie's Telegram bot account."""

from __future__ import annotations

from typing import Union

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.features.accounts import AccountPrincipal
from app.features.communication import (
    ConfigureTelegramAccountCommand,
    CreateTelegramPairingSessionCommand,
    DisconnectTelegramAccountCommand,
    GetTelegramAccountQuery,
    TelegramAccountConflict,
    TelegramAccountError,
    TelegramAccountInvalid,
    TelegramAccountNotFound,
    TelegramAccountsService,
)
from app.interfaces.api.v1.auth import require_user

from .dependencies import telegram_accounts_service
from .models import (
    TelegramAccountErrorDetails,
    TelegramAccountErrorItem,
    TelegramAccountErrorResponse,
    TelegramAccountResponse,
    TelegramAccountUpdateRequest,
    TelegramPairingSessionResponse,
)

router = APIRouter(
    prefix="/api/v1/elfies/{elfie_id}/communication-accounts/telegram",
    tags=["elfie-communication-accounts"],
)
CurrentPrincipal = Depends(require_user)
TelegramService = Depends(telegram_accounts_service)


@router.get("", response_model=TelegramAccountResponse)
def get_telegram_account(
    elfie_id: str,
    principal: AccountPrincipal = CurrentPrincipal,
    service: TelegramAccountsService = TelegramService,
) -> Union[TelegramAccountResponse, JSONResponse]:
    try:
        result = service.get_account(principal, GetTelegramAccountQuery(elfie_id))
    except TelegramAccountError as error:
        return _error_response(error)
    return TelegramAccountResponse.from_result(result)


@router.put("", response_model=TelegramAccountResponse)
def configure_telegram_account(
    elfie_id: str,
    body: TelegramAccountUpdateRequest,
    principal: AccountPrincipal = CurrentPrincipal,
    service: TelegramAccountsService = TelegramService,
) -> Union[TelegramAccountResponse, JSONResponse]:
    try:
        result = service.configure_account(
            principal,
            ConfigureTelegramAccountCommand(elfie_id, body.bot_token),
        )
    except TelegramAccountError as error:
        return _error_response(error)
    return TelegramAccountResponse.from_result(result)


@router.delete("", response_model=TelegramAccountResponse)
def disconnect_telegram_account(
    elfie_id: str,
    principal: AccountPrincipal = CurrentPrincipal,
    service: TelegramAccountsService = TelegramService,
) -> Union[TelegramAccountResponse, JSONResponse]:
    try:
        result = service.disconnect_account(
            principal, DisconnectTelegramAccountCommand(elfie_id)
        )
    except TelegramAccountError as error:
        return _error_response(error)
    return TelegramAccountResponse.from_result(result)


@router.post(
    "/pairing-sessions",
    status_code=201,
    response_model=TelegramPairingSessionResponse,
)
def create_telegram_pairing_session(
    elfie_id: str,
    principal: AccountPrincipal = CurrentPrincipal,
    service: TelegramAccountsService = TelegramService,
) -> Union[TelegramPairingSessionResponse, JSONResponse]:
    try:
        result = service.create_pairing_session(
            principal, CreateTelegramPairingSessionCommand(elfie_id)
        )
    except TelegramAccountError as error:
        return _error_response(error)
    return TelegramPairingSessionResponse.from_result(result)


def _error_response(error: TelegramAccountError) -> JSONResponse:
    status_code = 503
    code = "telegram_account_unavailable"
    if isinstance(error, TelegramAccountNotFound):
        status_code = 404
        code = "telegram_account_not_found"
    elif isinstance(error, TelegramAccountInvalid):
        status_code = 422
        code = "telegram_account_invalid"
    elif isinstance(error, TelegramAccountConflict):
        status_code = 409
        code = "telegram_account_conflict"
    payload = TelegramAccountErrorResponse(
        error=TelegramAccountErrorItem(
            code=code,
            message=str(error),
            details=TelegramAccountErrorDetails(),
        )
    )
    return JSONResponse(
        status_code=status_code, content=payload.model_dump(mode="json")
    )


__all__ = ("router",)
