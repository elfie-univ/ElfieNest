"""Versioned current-member Communication resources."""

from __future__ import annotations

from typing import Union

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.features.accounts import AccountPrincipal
from app.features.communication import (
    CommunicationError,
    CommunicationFacade,
    CommunicationUnavailable,
    ConversationNotFound,
    ListConversationsQuery,
    ListMessagesQuery,
    MessageInvalid,
    MessageResult,
)
from app.interfaces.api.runtime_capability import (
    RuntimeCapabilityDenied,
    require_runtime_capability,
)
from app.interfaces.api.v1.auth import require_user
from app.orchestration.message_delivery import (
    DuplicateMessage,
    MessageDeliveryError,
    MessageDeliveryFacade,
    MessageDeliveryUnavailable,
    MessageRejected,
    SubmitUserMessageCommand,
)

from .models import (
    CommunicationErrorDetails,
    CommunicationErrorItem,
    CommunicationErrorResponse,
    ConversationResponse,
    ConversationsResponse,
    MessageCreateRequest,
    MessageResponse,
    MessagesResponse,
)

router = APIRouter(prefix="/api/v1/me/conversations", tags=["me-conversations"])
CurrentPrincipal = Depends(require_user)


def communication_facade(request: Request) -> CommunicationFacade:
    facade = getattr(request.app.state, "communication", None)
    if not isinstance(facade, CommunicationFacade):
        raise CommunicationUnavailable("Communication service unavailable")
    return facade


def delivery_facade(request: Request) -> MessageDeliveryFacade:
    facade = getattr(request.app.state, "message_delivery", None)
    if not isinstance(facade, MessageDeliveryFacade):
        raise MessageDeliveryUnavailable("elfie_runtime_unavailable")
    return facade


@router.get(
    "",
    response_model=ConversationsResponse,
    responses={
        404: {"model": CommunicationErrorResponse},
        503: {"model": CommunicationErrorResponse},
    },
)
def list_conversations(
    request: Request,
    principal: AccountPrincipal = CurrentPrincipal,
) -> Union[ConversationsResponse, JSONResponse]:
    try:
        result = communication_facade(request).list_conversations(
            principal,
            ListConversationsQuery(),
        )
    except CommunicationError as error:
        return communication_error_response(error)
    return ConversationsResponse(
        items=[
            ConversationResponse(
                elfie_id=item.elfie_id,
                name=item.name,
                portrait_url=item.portrait_url,
                last_message_preview=item.last_message_preview,
                last_message_at=item.last_message_at,
            )
            for item in result.items
        ]
    )


@router.get(
    "/{elfie_id}/messages",
    response_model=MessagesResponse,
    responses={
        404: {"model": CommunicationErrorResponse},
        503: {"model": CommunicationErrorResponse},
    },
)
def list_messages(
    elfie_id: str,
    request: Request,
    principal: AccountPrincipal = CurrentPrincipal,
) -> Union[MessagesResponse, JSONResponse]:
    try:
        result = communication_facade(request).list_messages(
            principal,
            ListMessagesQuery(elfie_id=elfie_id),
        )
    except CommunicationError as error:
        return communication_error_response(error)
    return MessagesResponse(items=[_message_response(item) for item in result.items])


@router.post(
    "/{elfie_id}/messages",
    status_code=201,
    response_model=MessageResponse,
    responses={
        404: {"model": CommunicationErrorResponse},
        409: {"model": CommunicationErrorResponse},
        422: {"model": CommunicationErrorResponse},
        503: {"model": CommunicationErrorResponse},
    },
)
def submit_message(
    elfie_id: str,
    body: MessageCreateRequest,
    request: Request,
    principal: AccountPrincipal = CurrentPrincipal,
) -> Union[MessageResponse, JSONResponse]:
    try:
        require_runtime_capability(request.app, "chat")
        result = delivery_facade(request).submit_user_message(
            principal,
            SubmitUserMessageCommand(elfie_id=elfie_id, text=body.text),
        )
    except RuntimeCapabilityDenied as error:
        return capability_error_response(error)
    except CommunicationError as error:
        return communication_error_response(error)
    except MessageDeliveryError as error:
        return delivery_error_response(error)
    return _message_response(result.message)


def communication_error_response(error: CommunicationError) -> JSONResponse:
    status_code = 503
    code = "communication_unavailable"
    if isinstance(error, ConversationNotFound):
        status_code = 404
        code = "conversation_not_found"
    elif isinstance(error, MessageInvalid):
        status_code = 422
        code = "message_invalid"
    body = CommunicationErrorResponse(
        error=CommunicationErrorItem(
            code=code,
            message=str(error),
            details=CommunicationErrorDetails(),
        )
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def delivery_error_response(error: MessageDeliveryError) -> JSONResponse:
    status_code = 409
    code = str(error)
    if isinstance(error, MessageDeliveryUnavailable):
        status_code = 503
    elif isinstance(error, DuplicateMessage):
        code = "duplicate_message"
    elif not isinstance(error, MessageRejected):
        code = "message_delivery_failed"
    body = CommunicationErrorResponse(
        error=CommunicationErrorItem(
            code=code,
            message=str(error),
            details=CommunicationErrorDetails(),
        )
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def capability_error_response(error: RuntimeCapabilityDenied) -> JSONResponse:
    body = CommunicationErrorResponse(
        error=CommunicationErrorItem(
            code=error.code,
            message=error.detail,
            details=CommunicationErrorDetails(),
        )
    )
    return JSONResponse(status_code=503, content=body.model_dump(mode="json"))


def _message_response(message: MessageResult) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        elfie_id=message.elfie_id,
        sender=message.sender,
        text=message.text,
        created_at=message.created_at,
    )


__all__ = (
    "communication_error_response",
    "capability_error_response",
    "communication_facade",
    "delivery_error_response",
    "delivery_facade",
    "router",
)
