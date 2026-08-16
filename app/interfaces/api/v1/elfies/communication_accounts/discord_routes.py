"""Versioned owner routes for one Elfie's Discord Bot account."""

from __future__ import annotations

from typing import Union

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.features.accounts import AccountPrincipal
from app.features.communication import (
    ConfigureDiscordAccountCommand,
    CreateDiscordPairingSessionCommand,
    DisconnectDiscordAccountCommand,
    DiscordAccountConflict,
    DiscordAccountError,
    DiscordAccountInvalid,
    DiscordAccountNotFound,
    DiscordAccountsService,
    GetDiscordAccountQuery,
)
from app.interfaces.api.v1.auth import require_user

from .discord_dependencies import discord_accounts_service
from .discord_models import (
    DiscordAccountErrorDetails,
    DiscordAccountErrorItem,
    DiscordAccountErrorResponse,
    DiscordAccountResponse,
    DiscordAccountUpdateRequest,
    DiscordPairingSessionResponse,
)

router = APIRouter(
    prefix="/api/v1/elfies/{elfie_id}/communication-accounts/discord",
    tags=["elfie-communication-accounts"],
)
CurrentPrincipal = Depends(require_user)
DiscordService = Depends(discord_accounts_service)


@router.get("", response_model=DiscordAccountResponse)
def get_discord_account(
    elfie_id: str,
    principal: AccountPrincipal = CurrentPrincipal,
    service: DiscordAccountsService = DiscordService,
) -> Union[DiscordAccountResponse, JSONResponse]:
    try:
        result = service.get_account(principal, GetDiscordAccountQuery(elfie_id))
    except DiscordAccountError as error:
        return _error_response(error)
    return DiscordAccountResponse.from_result(result)


@router.put("", response_model=DiscordAccountResponse)
def configure_discord_account(
    elfie_id: str,
    body: DiscordAccountUpdateRequest,
    principal: AccountPrincipal = CurrentPrincipal,
    service: DiscordAccountsService = DiscordService,
) -> Union[DiscordAccountResponse, JSONResponse]:
    try:
        result = service.configure_account(
            principal,
            ConfigureDiscordAccountCommand(elfie_id, body.bot_token),
        )
    except DiscordAccountError as error:
        return _error_response(error)
    return DiscordAccountResponse.from_result(result)


@router.delete("", response_model=DiscordAccountResponse)
def disconnect_discord_account(
    elfie_id: str,
    principal: AccountPrincipal = CurrentPrincipal,
    service: DiscordAccountsService = DiscordService,
) -> Union[DiscordAccountResponse, JSONResponse]:
    try:
        result = service.disconnect_account(
            principal, DisconnectDiscordAccountCommand(elfie_id)
        )
    except DiscordAccountError as error:
        return _error_response(error)
    return DiscordAccountResponse.from_result(result)


@router.post(
    "/pairing-sessions",
    status_code=201,
    response_model=DiscordPairingSessionResponse,
)
def create_discord_pairing_session(
    elfie_id: str,
    principal: AccountPrincipal = CurrentPrincipal,
    service: DiscordAccountsService = DiscordService,
) -> Union[DiscordPairingSessionResponse, JSONResponse]:
    try:
        result = service.create_pairing_session(
            principal, CreateDiscordPairingSessionCommand(elfie_id)
        )
    except DiscordAccountError as error:
        return _error_response(error)
    return DiscordPairingSessionResponse.from_result(result)


def _error_response(error: DiscordAccountError) -> JSONResponse:
    status_code = 503
    code = "discord_account_unavailable"
    if isinstance(error, DiscordAccountNotFound):
        status_code = 404
        code = "discord_account_not_found"
    elif isinstance(error, DiscordAccountInvalid):
        status_code = 422
        code = "discord_account_invalid"
    elif isinstance(error, DiscordAccountConflict):
        status_code = 409
        code = "discord_account_conflict"
    payload = DiscordAccountErrorResponse(
        error=DiscordAccountErrorItem(
            code=code,
            message=str(error),
            details=DiscordAccountErrorDetails(),
        )
    )
    return JSONResponse(
        status_code=status_code, content=payload.model_dump(mode="json")
    )


__all__ = ("router",)
