"""Strict version-one WebSocket protocol for authenticated external bodies."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from elfie.body.contracts import BodyCommand, BodySensorEvent, CommandReceipt


class StrictFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BodyFrameBase(StrictFrame):
    protocol_version: Literal["1"]
    event_id: str = Field(min_length=1, max_length=160)
    occurred_at: datetime


class BodyHeartbeatFrame(BodyFrameBase):
    event: Literal["heartbeat"]


class BodySensorFrame(BodyFrameBase):
    event: Literal["sensor_event"]
    sensor_event: BodySensorEvent


class BodyReceiptFrame(BodyFrameBase):
    event: Literal["receipt"]
    receipt: CommandReceipt


class BodyCommandPollFrame(BodyFrameBase):
    event: Literal["command_poll"]


BodyProtocolFrame = Annotated[
    Union[
        BodyHeartbeatFrame,
        BodySensorFrame,
        BodyReceiptFrame,
        BodyCommandPollFrame,
    ],
    Field(discriminator="event"),
]
BODY_FRAME_ADAPTER: TypeAdapter[BodyProtocolFrame] = TypeAdapter(BodyProtocolFrame)


class BodyServerFrameBase(StrictFrame):
    protocol_version: Literal["1"] = "1"
    event_id: str
    occurred_at: datetime


class BodyIdentityPayload(StrictFrame):
    body_id: str


class BodyDeliveryPayload(StrictFrame):
    delivered: bool


class BodyCommandsPayload(StrictFrame):
    commands: list[BodyCommand]


class BodyErrorPayload(StrictFrame):
    code: Literal["invalid_body_frame", "body_identity_mismatch"]


class BodyReadyServerFrame(BodyServerFrameBase):
    event: Literal["ready"] = "ready"
    payload: BodyIdentityPayload


class BodyHeartbeatServerFrame(BodyServerFrameBase):
    event: Literal["heartbeat"] = "heartbeat"
    payload: BodyIdentityPayload


class BodySensorServerFrame(BodyServerFrameBase):
    event: Literal["sensor_event"] = "sensor_event"
    payload: BodyDeliveryPayload


class BodyReceiptServerFrame(BodyServerFrameBase):
    event: Literal["receipt"] = "receipt"
    payload: BodyDeliveryPayload


class BodyCommandsServerFrame(BodyServerFrameBase):
    event: Literal["commands"] = "commands"
    payload: BodyCommandsPayload


class BodyErrorServerFrame(BodyServerFrameBase):
    event: Literal["error"] = "error"
    payload: BodyErrorPayload


BodyServerFrame = Union[
    BodyReadyServerFrame,
    BodyHeartbeatServerFrame,
    BodySensorServerFrame,
    BodyReceiptServerFrame,
    BodyCommandsServerFrame,
    BodyErrorServerFrame,
]


__all__ = (
    "BODY_FRAME_ADAPTER",
    "BodyCommandPollFrame",
    "BodyCommandsPayload",
    "BodyCommandsServerFrame",
    "BodyDeliveryPayload",
    "BodyErrorPayload",
    "BodyErrorServerFrame",
    "BodyHeartbeatFrame",
    "BodyHeartbeatServerFrame",
    "BodyIdentityPayload",
    "BodyProtocolFrame",
    "BodyReceiptFrame",
    "BodyReceiptServerFrame",
    "BodyReadyServerFrame",
    "BodySensorFrame",
    "BodySensorServerFrame",
    "BodyServerFrame",
)
