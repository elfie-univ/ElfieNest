"""Godot Runtime protocol v2 typed frames."""

from __future__ import annotations

from datetime import datetime
from enum import Enum, unique
from typing import Dict, List, Literal, Optional, Type

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator
from typing_extensions import TypeAlias

JsonObject: TypeAlias = Dict[str, JsonValue]


@unique
class CommandName(str, Enum):
    """Python Nest 向 Godot Runtime 发送的封闭命令。"""

    CONFIGURE_WORLD = "configure_world"
    SYNC_ACTORS = "sync_actors"
    EXECUTE_INTENT = "execute_intent"
    CANCEL_INTENT = "cancel_intent"


@unique
class EventName(str, Enum):
    """Godot Runtime 向 Python Nest 回传的封闭事件。"""

    WORLD_READY = "world_ready"
    SCENE_MANIFEST = "scene_manifest"
    WORLD_SNAPSHOT = "world_snapshot"
    CONFIG_REJECTED = "config_rejected"
    STARTUP_ERROR = "startup_error"
    INTENT_ACCEPTED = "intent_accepted"
    INTENT_STARTED = "intent_started"
    INTENT_TERMINAL = "intent_terminal"
    MOVEMENT_BLOCKED = "movement_blocked"
    TACTILE_CONTACT = "tactile_contact"
    SPEECH_AUDIENCE = "speech_audience"


@unique
class IntentTerminalStatus(str, Enum):
    """Runtime intent 的唯一终态。"""

    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class _Payload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class _WorldReadyPayload(_Payload):
    ready: bool
    navigation_ready: bool = False


class _ManifestZonePayload(_Payload):
    zone_id: str
    kind: str
    label: str
    stable_order: int = Field(ge=0)
    active: bool


class _ManifestAnchorPayload(_Payload):
    anchor_id: str
    zone_id: str
    kind: Literal["bed", "chair", "door", "activity"]
    label: str
    stable_order: int = Field(ge=0)
    active: bool


class _SceneManifestPayload(_Payload):
    nest_id: str
    world_revision: int = Field(ge=0)
    bed_count: int = Field(ge=1, le=32)
    capabilities: List[str] = Field(default_factory=list)
    zones: List[_ManifestZonePayload]
    anchors: List[_ManifestAnchorPayload]


class _SnapshotActorPayload(_Payload):
    actor_id: str
    zone_id: Optional[str]
    posture: str
    active_command_id: Optional[str]


class _WorldSnapshotPayload(_Payload):
    world_revision: int = Field(ge=0)
    actors: List[_SnapshotActorPayload]


class _StartupFailurePayload(_Payload):
    code: str
    accepted: Optional[bool] = None
    world_revision: Optional[int] = Field(default=None, ge=0)


class _IntentProgressPayload(_Payload):
    command_id: str
    actor_id: str


class _IntentTerminalPayload(_IntentProgressPayload):
    status: IntentTerminalStatus
    reason: Optional[str] = None
    detail: Optional[str] = None


class _MovementBlockedPayload(_IntentProgressPayload):
    pass


class _TactileContactPayload(_Payload):
    actor_id: str
    intensity: float = Field(ge=0.0, le=1.0)
    direction: str
    contact_kind: Literal["actor", "world"]
    source_semantic_id: str


class _SpeechAudiencePayload(_IntentProgressPayload):
    text: str
    zone_id: str
    audience_actor_ids: List[str]


class _ConfigureWorldPayload(_Payload):
    nest_id: str = Field(min_length=1)
    bed_count: int = Field(ge=1, le=32)
    world_revision: int = Field(ge=0)


class _ActorDescriptorPayload(_Payload):
    actor_id: str = Field(min_length=1)
    species: str = Field(min_length=1)
    home_anchor_id: str = Field(min_length=1)
    appearance: JsonObject


class _SyncActorsPayload(_Payload):
    actors: List[_ActorDescriptorPayload]


class _ExecuteIntentPayload(_Payload):
    command_id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    intent: Literal["move_to_anchor", "speak", "emotion_expression"]
    deadline_seconds: float = Field(gt=0.0)
    anchor_id: Optional[str] = None
    text: Optional[str] = None
    expression: Optional[str] = None

    @model_validator(mode="after")
    def _validate_intent_fields(self) -> _ExecuteIntentPayload:
        required = {
            "move_to_anchor": self.anchor_id,
            "speak": self.text,
            "emotion_expression": self.expression,
        }
        value = required[self.intent]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{self.intent} payload is incomplete")
        supplied = {
            name
            for name, field_value in {
                "anchor_id": self.anchor_id,
                "text": self.text,
                "expression": self.expression,
            }.items()
            if field_value is not None
        }
        expected = {
            "move_to_anchor": {"anchor_id"},
            "speak": {"text"},
            "emotion_expression": {"expression"},
        }[self.intent]
        if supplied != expected:
            raise ValueError(f"{self.intent} payload has incompatible fields")
        return self


class _CancelIntentPayload(_Payload):
    command_id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)


_COMMAND_PAYLOAD_MODELS: Dict[CommandName, Type[_Payload]] = {
    CommandName.CONFIGURE_WORLD: _ConfigureWorldPayload,
    CommandName.SYNC_ACTORS: _SyncActorsPayload,
    CommandName.EXECUTE_INTENT: _ExecuteIntentPayload,
    CommandName.CANCEL_INTENT: _CancelIntentPayload,
}


_EVENT_PAYLOAD_MODELS: Dict[EventName, Type[_Payload]] = {
    EventName.WORLD_READY: _WorldReadyPayload,
    EventName.SCENE_MANIFEST: _SceneManifestPayload,
    EventName.WORLD_SNAPSHOT: _WorldSnapshotPayload,
    EventName.CONFIG_REJECTED: _StartupFailurePayload,
    EventName.STARTUP_ERROR: _StartupFailurePayload,
    EventName.INTENT_ACCEPTED: _IntentProgressPayload,
    EventName.INTENT_STARTED: _IntentProgressPayload,
    EventName.INTENT_TERMINAL: _IntentTerminalPayload,
    EventName.MOVEMENT_BLOCKED: _MovementBlockedPayload,
    EventName.TACTILE_CONTACT: _TactileContactPayload,
    EventName.SPEECH_AUDIENCE: _SpeechAudiencePayload,
}

_COMMAND_CORRELATED_EVENTS = {
    EventName.INTENT_ACCEPTED,
    EventName.INTENT_STARTED,
    EventName.INTENT_TERMINAL,
    EventName.MOVEMENT_BLOCKED,
    EventName.SPEECH_AUDIENCE,
}


class _RuntimeFrame(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    protocol: Literal[2]
    message_id: str
    runtime_id: str
    generation: int = Field(ge=0)
    world_revision: int = Field(ge=0)
    correlation_id: Optional[str] = None
    payload: JsonObject


class RuntimeCommandFrame(_RuntimeFrame):
    """Strict outbound command frame for protocol v2."""

    kind: Literal["command"]
    name: CommandName
    issued_at: datetime

    @model_validator(mode="after")
    def _validate_named_payload(self) -> RuntimeCommandFrame:
        _COMMAND_PAYLOAD_MODELS[self.name].model_validate(self.payload)
        if self.name is CommandName.CONFIGURE_WORLD:
            if self.payload.get("world_revision") != self.world_revision:
                raise ValueError("configure payload revision must equal frame revision")
        if self.name in {
            CommandName.EXECUTE_INTENT,
            CommandName.CANCEL_INTENT,
        }:
            command_id = self.payload.get("command_id")
            if self.correlation_id != command_id:
                raise ValueError("command correlation_id must equal command_id")
        return self


class RuntimeEventFrame(_RuntimeFrame):
    """Strict inbound event frame for protocol v2."""

    kind: Literal["event"]
    name: EventName
    occurred_at: datetime

    @model_validator(mode="after")
    def _validate_named_payload(self) -> RuntimeEventFrame:
        _EVENT_PAYLOAD_MODELS[self.name].model_validate(self.payload)
        if self.name in _COMMAND_CORRELATED_EVENTS:
            command_id = self.payload.get("command_id")
            if self.correlation_id != command_id:
                raise ValueError("event correlation_id must equal command_id")
        return self


def parse_runtime_command_frame(raw: JsonObject) -> RuntimeCommandFrame:
    """Parse an untrusted outbound command frame into the v2 contract."""
    return RuntimeCommandFrame.model_validate(raw)


def parse_runtime_event_frame(raw: JsonObject) -> RuntimeEventFrame:
    """Parse an untrusted inbound event frame into the v2 contract."""
    return RuntimeEventFrame.model_validate(raw)
