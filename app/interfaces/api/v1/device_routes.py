"""Owner device provisioning and machine-authenticated LAN heartbeat gateway."""

from __future__ import annotations

import json
from typing import Annotated, Final, Literal, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket
from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from starlette.websockets import WebSocketDisconnect

from app.features.accounts.auth import AuthenticatedUser, require_owner
from app.infrastructure.devices import DeviceRegistry
from app.infrastructure.devices.registry import DeviceCredentialError, DeviceRecord
from app.infrastructure.persistence.interface_query_repository import (
    InterfaceQueryRepository,
)
from elfie.body.contracts import BodySensorEvent, CommandReceipt

router = APIRouter(prefix="/api/v1", tags=["v1-devices"])

MAX_DEVICE_FRAME_BYTES: Final = 64 * 1024


class DeviceEnrollRequest(BaseModel):
    elfie_id: str = Field(..., pattern=r"^[0-9]{8}$")
    display_name: str = Field(..., min_length=1, max_length=120)
    body_type: str = Field(..., min_length=1, max_length=80)


class BodyCredentialResponse(BaseModel):
    body_id: str
    bearer_token: str


class BodyRecordResponse(BaseModel):
    body_id: str
    display_name: str
    body_type: str
    status: str
    last_heartbeat_at: Optional[float]


class DetailResponse(BaseModel):
    detail: str


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
    elfie_id: str,
    owner: AuthenticatedUser = Depends(require_owner),  # noqa: B008
) -> list[BodyRecordResponse]:
    _require_owned_elfie(request, owner, elfie_id)
    return [
        _device_payload(record)
        for record in _registry(request).list_for_elfie(elfie_id)
    ]


@router.post("/owner/devices")
async def enroll_device(
    body: DeviceEnrollRequest,
    request: Request,
    owner: AuthenticatedUser = Depends(require_owner),  # noqa: B008
) -> BodyCredentialResponse:
    _require_owned_elfie(request, owner, body.elfie_id)
    credential = _registry(request).enroll(
        body.elfie_id, body.display_name, body.body_type
    )
    return BodyCredentialResponse(
        body_id=credential.body_id, bearer_token=credential.bearer_token
    )


@router.post("/owner/devices/{body_id}/rotate")
async def rotate_device(
    body_id: str,
    request: Request,
    elfie_id: str,
    owner: AuthenticatedUser = Depends(require_owner),  # noqa: B008
) -> BodyCredentialResponse:
    _require_owned_elfie(request, owner, elfie_id)
    try:
        credential = _registry(request).rotate(elfie_id, body_id)
    except DeviceCredentialError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return BodyCredentialResponse(
        body_id=credential.body_id, bearer_token=credential.bearer_token
    )


@router.delete("/owner/devices/{body_id}")
async def revoke_device(
    body_id: str,
    request: Request,
    elfie_id: str,
    owner: AuthenticatedUser = Depends(require_owner),  # noqa: B008
) -> DetailResponse:
    _require_owned_elfie(request, owner, elfie_id)
    try:
        _registry(request).revoke(elfie_id, body_id)
    except DeviceCredentialError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return DetailResponse(detail="设备已撤销")


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
    gateway.connect_device(device.body_id)
    await websocket.send_json({"event": "ready", "body_id": device.body_id})
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
            registry.heartbeat(device.body_id)
            # CPython 3.9.25 is the supported runtime, so structural matching is unavailable.
            if isinstance(frame, DeviceHeartbeatFrame):
                await websocket.send_json(
                    {"event": "heartbeat", "body_id": device.body_id}
                )
            elif isinstance(frame, DeviceSensorFrame):
                delivered = gateway.deliver_sensor_event(
                    device.body_id, frame.sensor_event
                )
                registry.record_protocol_event(device.body_id, "sensor_event")
                await websocket.send_json(
                    {"event": "sensor_event", "delivered": delivered}
                )
            elif isinstance(frame, DeviceReceiptFrame):
                delivered = gateway.deliver_receipt(device.body_id, frame.receipt)
                registry.record_protocol_event(device.body_id, "receipt")
                await websocket.send_json({"event": "receipt", "delivered": delivered})
            elif isinstance(frame, DeviceCommandPollFrame):
                commands = gateway.drain_commands(device.body_id)
                registry.record_protocol_event(device.body_id, "command_poll")
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
        gateway.disconnect_device(device.body_id)


def _parse_device_frame(raw_frame: str) -> DeviceProtocolFrame | None:
    """Reject oversized, malformed, and unknown device JSON before dispatch."""
    if len(raw_frame.encode("utf-8")) > MAX_DEVICE_FRAME_BYTES:
        return None
    try:
        json.loads(raw_frame)
        return _DEVICE_FRAME_ADAPTER.validate_json(raw_frame)
    except (json.JSONDecodeError, ValidationError):
        return None


def _device_payload(record: DeviceRecord) -> BodyRecordResponse:
    return BodyRecordResponse(
        body_id=record.body_id,
        display_name=record.display_name,
        body_type=record.body_type,
        status=record.status,
        last_heartbeat_at=record.last_heartbeat_at,
    )


def _require_owned_elfie(
    request: Request, owner: AuthenticatedUser, elfie_id: str
) -> None:
    record = InterfaceQueryRepository(request.app.state.db_path).get_elfie(
        elfie_id, owner_user_id=owner["user_id"]
    )
    if record is None:
        raise HTTPException(status_code=404, detail="精灵不存在")
