"""Versioned, independently authenticated external-body WebSocket."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Final, Literal
from uuid import uuid4

from fastapi import APIRouter, WebSocket
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

from app.features.bodies import (
    BodiesUnavailable,
    BodyCredentialRejected,
    BodyPrincipal,
)
from app.orchestration.embodiment import BodyDeviceChannel, BodyProtocolRejected

from .models import (
    BODY_FRAME_ADAPTER,
    BodyCommandPollFrame,
    BodyHeartbeatFrame,
    BodyProtocolFrame,
    BodyReceiptFrame,
    BodySensorFrame,
    BodyServerFrame,
)

router = APIRouter(prefix="/api/v1/ws", tags=["realtime-bodies"])
MAX_BODY_FRAME_BYTES: Final = 64 * 1024


@router.websocket("/bodies")
async def body_websocket(websocket: WebSocket) -> None:
    authorization = websocket.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme != "Bearer" or not token:
        await websocket.close(code=1008)
        return
    channel = getattr(websocket.app.state, "body_device_channel", None)
    if not isinstance(channel, BodyDeviceChannel):
        await websocket.close(code=1011)
        return
    try:
        principal = channel.authenticate(token)
    except (BodyCredentialRejected, BodiesUnavailable):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    channel.connect(principal)
    await _send(websocket, "ready", {"body_id": principal.body_id})
    try:
        await _receive_loop(websocket, channel, principal, token)
    finally:
        channel.disconnect(principal)


async def _receive_loop(
    websocket: WebSocket,
    channel: BodyDeviceChannel,
    principal: BodyPrincipal,
    token: str,
) -> None:
    while True:
        try:
            raw_frame = await websocket.receive_text()
        except WebSocketDisconnect:
            return
        try:
            channel.authenticate(token)
        except (BodyCredentialRejected, BodiesUnavailable):
            await websocket.close(code=1008)
            return
        frame = _parse_body_frame(raw_frame)
        if frame is None:
            await _send(websocket, "error", {"code": "invalid_body_frame"})
            continue
        try:
            await _dispatch(websocket, channel, principal, frame)
        except BodyProtocolRejected:
            await _send(websocket, "error", {"code": "body_identity_mismatch"})


async def _dispatch(
    websocket: WebSocket,
    channel: BodyDeviceChannel,
    principal: BodyPrincipal,
    frame: BodyProtocolFrame,
) -> None:
    if isinstance(frame, BodyHeartbeatFrame):
        channel.heartbeat(principal)
        await _send(websocket, "heartbeat", {"body_id": principal.body_id})
    elif isinstance(frame, BodySensorFrame):
        delivered = channel.deliver_sensor(principal, frame.sensor_event)
        await _send(websocket, "sensor_event", {"delivered": delivered})
    elif isinstance(frame, BodyReceiptFrame):
        delivered = channel.deliver_receipt(principal, frame.receipt)
        await _send(websocket, "receipt", {"delivered": delivered})
    elif isinstance(frame, BodyCommandPollFrame):
        commands = channel.poll_commands(principal)
        await _send(
            websocket,
            "commands",
            {"commands": [command.model_dump(mode="json") for command in commands]},
        )
    else:
        raise RuntimeError("Unable to dispatch validated body frame")


def _parse_body_frame(raw_frame: str) -> BodyProtocolFrame | None:
    if len(raw_frame.encode("utf-8")) > MAX_BODY_FRAME_BYTES:
        return None
    try:
        json.loads(raw_frame)
        return BODY_FRAME_ADAPTER.validate_json(raw_frame)
    except (json.JSONDecodeError, ValidationError):
        return None


async def _send(
    websocket: WebSocket,
    event: Literal[
        "ready",
        "heartbeat",
        "sensor_event",
        "receipt",
        "commands",
        "error",
    ],
    payload: dict[str, object],
) -> None:
    frame = BodyServerFrame(
        event_id=f"body_event_{uuid4().hex}",
        occurred_at=datetime.now(timezone.utc),
        event=event,
        payload=payload,
    )
    await websocket.send_json(frame.model_dump(mode="json"))


__all__ = ("router",)
