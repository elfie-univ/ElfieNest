"""Strict same-origin WebSocket boundary for product message delivery."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fastapi import APIRouter, WebSocket
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

from app.features.communication import CommunicationError
from app.orchestration.message_delivery import (
    DuplicateMessage,
    MessageDeliveryError,
    MessageDeliveryFacade,
    SubmitUserMessageCommand,
)

from .models import (
    ChatErrorEvent,
    ChatMessageEvent,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatPrincipalResponse,
    ChatReadyEvent,
)

router = APIRouter(prefix="/api/v1", tags=["realtime-chat"])


@runtime_checkable
class ChatConnectionHub(Protocol):
    async def connect(self, user_id: int, websocket: WebSocket) -> None: ...

    async def disconnect(self, user_id: int, websocket: WebSocket) -> None: ...


@router.websocket("/ws/chat")
async def chat_websocket(websocket: WebSocket) -> None:
    policy = websocket.app.state.service_access_policy
    origin = websocket.headers.get("origin")
    if policy.mode.value == "lan" and (
        origin is None or not policy.allows_origin(origin)
    ):
        await websocket.close(code=1008)
        return
    token = websocket.cookies.get("session_token")
    principal = (
        websocket.app.state.accounts.authenticate_session(token) if token else None
    )
    delivery = getattr(websocket.app.state, "message_delivery", None)
    connections = getattr(websocket.app.state, "communication_realtime", None)
    if (
        principal is None
        or not isinstance(delivery, MessageDeliveryFacade)
        or not isinstance(connections, ChatConnectionHub)
    ):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    await connections.connect(principal.user_id, websocket)
    await websocket.send_json(
        ChatReadyEvent(
            principal=ChatPrincipalResponse(
                role=principal.role,
                account_id=principal.account_id,
            )
        ).model_dump(mode="json")
    )
    try:
        while True:
            payload = await websocket.receive_json()
            if not isinstance(payload, dict) or payload.get("event") != "user_message":
                await _send_error(websocket, "不支持的聊天事件")
                continue
            try:
                incoming = ChatMessageRequest.model_validate(payload)
            except ValidationError:
                await _send_error(websocket, "聊天字段无效")
                continue
            try:
                result = delivery.submit_user_message(
                    principal,
                    SubmitUserMessageCommand(
                        elfie_id=incoming.elfie_id,
                        text=incoming.text,
                    ),
                )
            except CommunicationError as error:
                await _send_error(websocket, str(error))
                continue
            except MessageDeliveryError as error:
                detail = (
                    "duplicate_message"
                    if isinstance(error, DuplicateMessage)
                    else str(error)
                )
                await _send_error(websocket, detail)
                continue
            await websocket.send_json(
                ChatMessageEvent(
                    message=ChatMessageResponse(
                        id=result.message.id,
                        elfie_id=result.message.elfie_id,
                        sender=result.message.sender,
                        text=result.message.text,
                        created_at=result.message.created_at,
                    )
                ).model_dump(mode="json")
            )
    except WebSocketDisconnect:
        pass
    finally:
        await connections.disconnect(principal.user_id, websocket)


async def _send_error(websocket: WebSocket, detail: str) -> None:
    await websocket.send_json(ChatErrorEvent(detail=detail).model_dump(mode="json"))


__all__ = ("ChatConnectionHub", "chat_websocket", "router")
