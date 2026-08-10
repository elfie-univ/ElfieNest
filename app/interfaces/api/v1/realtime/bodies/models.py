"""Strict version-one WebSocket protocol for authenticated external bodies."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from elfie.body.contracts import BodySensorEvent, CommandReceipt


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


class BodyServerFrame(StrictFrame):
    protocol_version: Literal["1"] = "1"
    event_id: str
    occurred_at: datetime
    event: Literal[
        "ready",
        "heartbeat",
        "sensor_event",
        "receipt",
        "commands",
        "error",
    ]
    payload: dict[str, Any]


__all__ = (
    "BODY_FRAME_ADAPTER",
    "BodyCommandPollFrame",
    "BodyHeartbeatFrame",
    "BodyProtocolFrame",
    "BodyReceiptFrame",
    "BodySensorFrame",
    "BodyServerFrame",
)
