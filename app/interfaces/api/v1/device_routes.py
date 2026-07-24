"""Owner device provisioning and machine-authenticated LAN heartbeat gateway."""

from __future__ import annotations

import json
from typing import Annotated, Any, Dict, Final, Literal, Union

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket
from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from starlette.websockets import WebSocketDisconnect

from app.features.accounts.auth import require_owner
from app.infrastructure.devices import DeviceRegistry
from app.infrastructure.devices.registry import DeviceCredentialError
from elfie.body.contracts import BodySensorEvent, CommandReceipt

router = APIRouter(prefix="/api/v1", tags=["v1-devices"])

MAX_DEVICE_FRAME_BYTES: Final = 64 * 1024


class DeviceEnrollRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=120)


class DeviceHeartbeatFrame(BaseModel):
    """Keep an authenticated device connection alive."""

    event: Literal["heartbeat"]


class DeviceSensorFrame(BaseModel):
    """One validated sensor observation from an external body."""

    event: Literal["sensor_event"]
    sensor_event: BodySensorEvent


class DeviceReceiptFrame(BaseModel):
    """One validated asynchronous command receipt from an external body."""

    event: Literal["receipt"]
    receipt: CommandReceipt


class DeviceCommandPollFrame(BaseModel):
    """Request each queued Core action exactly once."""

    event: Literal["command_poll"]


DeviceProtocolFrame = Annotated[
    Union[
        DeviceHeartbeatFrame,
        DeviceSensorFrame,
        DeviceReceiptFrame,
        DeviceCommandPollFrame,
    ],
    Field(discriminator="event"),
]
_DEVICE_FRAME_ADAPTER: Final[TypeAdapter[DeviceProtocolFrame]] = TypeAdapter(
    DeviceProtocolFrame
)


def _registry(request: Request) -> DeviceRegistry:
    return DeviceRegistry(request.app.state.db_path)


@router.get("/owner/devices")
async def list_devices(
    request: Request,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> list[Dict[str, Any]]:
    return [
        _device_payload(record)
        for record in _registry(request).list_for_owner(int(owner["id"]))
    ]


@router.post("/owner/devices")
async def enroll_device(
    body: DeviceEnrollRequest,
    request: Request,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, str]:
    credential = _registry(request).enroll(int(owner["id"]), body.display_name)
    return {"device_id": credential.device_id, "bearer_token": credential.bearer_token}


@router.post("/owner/devices/{device_id}/rotate")
async def rotate_device(
    device_id: str,
    request: Request,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, str]:
    try:
        credential = _registry(request).rotate(int(owner["id"]), device_id)
    except DeviceCredentialError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"device_id": credential.device_id, "bearer_token": credential.bearer_token}


@router.delete("/owner/devices/{device_id}")
async def revoke_device(
    device_id: str,
    request: Request,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, str]:
    try:
        _registry(request).revoke(int(owner["id"]), device_id)
    except DeviceCredentialError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"detail": "设备已撤销"}


@router.websocket("/ws/devices")
async def device_websocket(websocket: WebSocket) -> None:
    """Bridge authenticated LAN device frames to the typed external-body contract."""
    authorization = websocket.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme != "Bearer" or not token:
        await websocket.close(code=1008)
        return
    try:
        device = DeviceRegistry(websocket.app.state.db_path).authenticate(token)
    except DeviceCredentialError:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    gateway = websocket.app.state.device_gateway
    gateway.connect_device(device.device_id)
    await websocket.send_json({"event": "ready", "device_id": device.device_id})
    registry = DeviceRegistry(websocket.app.state.db_path)
    try:
        while True:
            try:
                raw_frame = await websocket.receive_text()
            except WebSocketDisconnect:
                return
            try:
                registry.authenticate(token)
            except DeviceCredentialError:
                await websocket.close(code=1008)
                return
            frame = _parse_device_frame(raw_frame)
            if frame is None:
                await websocket.send_json(
                    {"event": "error", "detail": "设备协议帧无效或过大"}
                )
                continue
            registry.heartbeat(device.device_id)
            # CPython 3.9.25 is the supported runtime, so structural matching is unavailable.
            if isinstance(frame, DeviceHeartbeatFrame):
                await websocket.send_json(
                    {"event": "heartbeat", "device_id": device.device_id}
                )
            elif isinstance(frame, DeviceSensorFrame):
                delivered = gateway.deliver_sensor_event(
                    device.device_id, frame.sensor_event
                )
                registry.record_protocol_event(device.device_id, "sensor_event")
                await websocket.send_json(
                    {"event": "sensor_event", "delivered": delivered}
                )
            elif isinstance(frame, DeviceReceiptFrame):
                delivered = gateway.deliver_receipt(device.device_id, frame.receipt)
                registry.record_protocol_event(device.device_id, "receipt")
                await websocket.send_json({"event": "receipt", "delivered": delivered})
            elif isinstance(frame, DeviceCommandPollFrame):
                commands = gateway.drain_commands(device.device_id)
                registry.record_protocol_event(device.device_id, "command_poll")
                await websocket.send_json(
                    {
                        "event": "commands",
                        "commands": [
                            command.model_dump(mode="json") for command in commands
                        ],
                    }
                )
            else:
                raise RuntimeError("无法分派已验证的设备协议帧")
    finally:
        gateway.disconnect_device(device.device_id)


def _parse_device_frame(raw_frame: str) -> DeviceProtocolFrame | None:
    """Reject oversized, malformed, and unknown device JSON before dispatch."""
    if len(raw_frame.encode("utf-8")) > MAX_DEVICE_FRAME_BYTES:
        return None
    try:
        json.loads(raw_frame)
        return _DEVICE_FRAME_ADAPTER.validate_json(raw_frame)
    except (json.JSONDecodeError, ValidationError):
        return None


def _device_payload(record) -> Dict[str, Any]:
    return {
        "device_id": record.device_id,
        "display_name": record.display_name,
        "revoked": record.revoked,
        "last_heartbeat_at": record.last_heartbeat_at,
    }
