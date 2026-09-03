"""Godot Runtime protocol v3 typed frames and semantic lanes."""

from __future__ import annotations

from datetime import datetime
from enum import Enum, unique
from typing import Dict, List, Literal, Optional, Tuple, Type

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator
from typing_extensions import TypeAlias

JsonObject: TypeAlias = Dict[str, JsonValue]


@unique
class CommandName(str, Enum):
    """Python Nest 向 Godot Runtime 发送的封闭命令。"""

    CONFIGURE_WORLD = "configure_world"
    SYNC_ACTORS = "sync_actors"
    REQUEST_SPEECH_REACH = "request_speech_reach"
    REQUEST_VISUAL_OBSERVATION = "request_visual_observation"
    APPLY_ENVIRONMENT = "apply_environment"
    EXECUTE_INTENT = "execute_intent"
    CANCEL_INTENT = "cancel_intent"


@unique
class EventName(str, Enum):
    """Godot Runtime 向 Python Nest 回传的封闭事件。"""

    WORLD_CONFIGURED = "world_configured"
    SCENE_MANIFEST = "scene_manifest"
    WORLD_SNAPSHOT = "world_snapshot"
    CONFIG_REJECTED = "config_rejected"
    STARTUP_ERROR = "startup_error"
    INTENT_ACCEPTED = "intent_accepted"
    INTENT_STARTED = "intent_started"
    INTENT_TERMINAL = "intent_terminal"
    MOVEMENT_BLOCKED = "movement_blocked"
    TACTILE_CONTACT = "tactile_contact"
    SPEECH_REACH = "speech_reach"
    VISUAL_OBSERVATION = "visual_observation"
    ENVIRONMENT_STATE = "environment_state"


@unique
class IntentTerminalStatus(str, Enum):
    """Runtime intent 的唯一终态。"""

    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class _Payload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


@unique
class SemanticLane(str, Enum):
    """One validated delivery lane on the shared Runtime connection."""

    RUNTIME = "runtime"
    BODY = "body"
    NEST = "nest"


class _WorldConfiguredPayload(_Payload):
    configured: bool
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


class _ManifestFacilityPayload(_Payload):
    facility_id: str
    zone_id: str
    kind: Literal["rest", "activity", "transit", "social"]
    label: str
    capabilities: List[str] = Field(default_factory=list)
    active: bool


class _SceneManifestPayload(_Payload):
    nest_id: str
    world_revision: int = Field(ge=0)
    bed_count: int = Field(ge=4, le=32)
    capabilities: List[str] = Field(default_factory=list)
    zones: List[_ManifestZonePayload]
    anchors: List[_ManifestAnchorPayload]
    facilities: List[_ManifestFacilityPayload] = Field(default_factory=list)


class _MockMotionPayload(_Payload):
    waypoint: int = Field(ge=0, le=5)
    sequence: int = Field(ge=1)


class _SnapshotActorPayload(_Payload):
    actor_id: str
    zone_id: Optional[str]
    posture: str
    active_command_id: Optional[str]
    mock_motion: Optional[_MockMotionPayload] = None
    position: Optional[Tuple[float, float, float]] = None
    heading_degrees: Optional[float] = None
    velocity: Optional[Tuple[float, float, float]] = None


class _WorldSnapshotPayload(_Payload):
    world_revision: int = Field(ge=0)
    actors: List[_SnapshotActorPayload]


class _StartupFailurePayload(_Payload):
    code: str
    accepted: Optional[bool] = None
    world_revision: Optional[int] = Field(default=None, ge=0)


class _CommandProgressPayload(_Payload):
    command_id: str
    actor_id: str


class _IntentProgressPayload(_CommandProgressPayload):
    intent_id: str
    body_generation: int = Field(ge=1)


class _IntentTerminalPayload(_IntentProgressPayload):
    status: IntentTerminalStatus
    reason: Optional[str] = None
    detail: Optional[str] = None


class _MovementBlockedPayload(_IntentProgressPayload):
    pass


class _TactileContactPayload(_Payload):
    actor_id: str
    body_generation: int = Field(default=1, ge=1)
    intensity: float = Field(ge=0.0, le=1.0)
    direction: str
    contact_kind: Literal["actor", "world"]
    source_semantic_id: str
    force_newtons: Optional[float] = Field(default=None, ge=0.0)


class _SpeechReachPayload(_CommandProgressPayload):
    zone_id: str
    audience_actor_ids: List[str]


class _RequestSpeechReachPayload(_Payload):
    command_id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    acoustic_profile: Literal["quiet", "normal", "loud"] = "normal"


class _VisualObservationPayload(_Payload):
    observation_id: str
    actor_id: str
    zone_id: str
    visible_semantic_ids: List[str] = Field(min_length=0, max_length=64)


class _RequestVisualObservationPayload(_Payload):
    observation_id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    max_results: int = Field(default=32, ge=1, le=64)


class _ApplyEnvironmentPayload(_Payload):
    object_id: str = Field(min_length=1)
    command_id: str = Field(min_length=1)
    lights_on: bool
    quiet_mode: bool


class _EnvironmentStatePayload(_Payload):
    object_id: str = Field(min_length=1)
    command_id: str = Field(min_length=1)
    lights_on: bool
    quiet_mode: bool
    applied: bool
    reason: Optional[str] = None


class _ConfigureWorldPayload(_Payload):
    nest_id: str = Field(min_length=1)
    bed_count: int = Field(ge=4, le=32)
    world_revision: int = Field(ge=0)


class _ActorDescriptorPayload(_Payload):
    actor_id: str = Field(min_length=1)
    species: str = Field(min_length=1)
    spawn_anchor_id: str = Field(min_length=1)
    appearance: JsonObject


class _SyncActorsPayload(_Payload):
    actors: List[_ActorDescriptorPayload]


class _ExecuteIntentPayload(_Payload):
    command_id: str = Field(min_length=1)
    intent_id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    body_generation: int = Field(ge=1)
    initiator: Literal["elfie"]
    intent: Literal[
        "move_to_anchor",
        "move_forward",
        "turn",
        "speak",
        "emotion_expression",
    ]
    deadline_seconds: float = Field(gt=0.0)
    anchor_id: Optional[str] = None
    distance: Optional[float] = Field(default=None, gt=0.0)
    angle_degrees: Optional[float] = Field(default=None, ge=-360.0, le=360.0)
    text: Optional[str] = None
    expression: Optional[str] = None
    intensity: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_intent_fields(self) -> _ExecuteIntentPayload:
        if self.intent == "speak":
            # The utterance is stored and routed by Nest before the direct
            # Body animation command.  The Godot command may therefore omit
            # text; a direct protocol caller may still include non-empty text.
            if self.text is not None and not self.text.strip():
                raise ValueError("speak payload is incomplete")
        elif self.intent == "move_to_anchor":
            required = {
                "move_to_anchor": self.anchor_id,
            }
            value = required["move_to_anchor"]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{self.intent} payload is incomplete")
        elif self.intent == "move_forward":
            if self.distance is None:
                raise ValueError("move_forward payload is incomplete")
        elif self.intent == "turn":
            if self.angle_degrees is None:
                raise ValueError("turn payload is incomplete")
        else:
            value = self.expression
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{self.intent} payload is incomplete")
        supplied = {
            name
            for name, field_value in {
                "anchor_id": self.anchor_id,
                "distance": self.distance,
                "angle_degrees": self.angle_degrees,
                "text": self.text,
                "expression": self.expression,
                "intensity": self.intensity,
            }.items()
            if field_value is not None
        }
        expected = {
            "move_to_anchor": {"anchor_id"},
            "move_forward": {"distance"},
            "turn": {"angle_degrees"},
            "speak": {"text"} if self.text is not None else set(),
            "emotion_expression": {"expression"},
        }[self.intent]
        if self.intent == "emotion_expression" and self.intensity is not None:
            expected = expected | {"intensity"}
        if supplied != expected:
            raise ValueError(f"{self.intent} payload has incompatible fields")
        return self


class _CancelIntentPayload(_Payload):
    command_id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)


_COMMAND_PAYLOAD_MODELS: Dict[CommandName, Type[_Payload]] = {
    CommandName.CONFIGURE_WORLD: _ConfigureWorldPayload,
    CommandName.SYNC_ACTORS: _SyncActorsPayload,
    CommandName.REQUEST_SPEECH_REACH: _RequestSpeechReachPayload,
    CommandName.REQUEST_VISUAL_OBSERVATION: _RequestVisualObservationPayload,
    CommandName.APPLY_ENVIRONMENT: _ApplyEnvironmentPayload,
    CommandName.EXECUTE_INTENT: _ExecuteIntentPayload,
    CommandName.CANCEL_INTENT: _CancelIntentPayload,
}


_EVENT_PAYLOAD_MODELS: Dict[EventName, Type[_Payload]] = {
    EventName.WORLD_CONFIGURED: _WorldConfiguredPayload,
    EventName.SCENE_MANIFEST: _SceneManifestPayload,
    EventName.WORLD_SNAPSHOT: _WorldSnapshotPayload,
    EventName.CONFIG_REJECTED: _StartupFailurePayload,
    EventName.STARTUP_ERROR: _StartupFailurePayload,
    EventName.INTENT_ACCEPTED: _IntentProgressPayload,
    EventName.INTENT_STARTED: _IntentProgressPayload,
    EventName.INTENT_TERMINAL: _IntentTerminalPayload,
    EventName.MOVEMENT_BLOCKED: _MovementBlockedPayload,
    EventName.TACTILE_CONTACT: _TactileContactPayload,
    EventName.SPEECH_REACH: _SpeechReachPayload,
    EventName.VISUAL_OBSERVATION: _VisualObservationPayload,
    EventName.ENVIRONMENT_STATE: _EnvironmentStatePayload,
}

_COMMAND_CORRELATED_EVENTS = {
    EventName.INTENT_ACCEPTED,
    EventName.INTENT_STARTED,
    EventName.INTENT_TERMINAL,
    EventName.MOVEMENT_BLOCKED,
    EventName.SPEECH_REACH,
    EventName.VISUAL_OBSERVATION,
    EventName.ENVIRONMENT_STATE,
}

_COMMAND_LANES = {
    CommandName.CONFIGURE_WORLD: SemanticLane.NEST,
    CommandName.SYNC_ACTORS: SemanticLane.NEST,
    CommandName.REQUEST_SPEECH_REACH: SemanticLane.NEST,
    CommandName.REQUEST_VISUAL_OBSERVATION: SemanticLane.NEST,
    CommandName.APPLY_ENVIRONMENT: SemanticLane.NEST,
    CommandName.EXECUTE_INTENT: SemanticLane.BODY,
    CommandName.CANCEL_INTENT: SemanticLane.BODY,
}

_EVENT_LANES = {
    EventName.WORLD_CONFIGURED: SemanticLane.NEST,
    EventName.SCENE_MANIFEST: SemanticLane.NEST,
    EventName.WORLD_SNAPSHOT: SemanticLane.NEST,
    EventName.CONFIG_REJECTED: SemanticLane.NEST,
    EventName.STARTUP_ERROR: SemanticLane.NEST,
    EventName.INTENT_ACCEPTED: SemanticLane.BODY,
    EventName.INTENT_STARTED: SemanticLane.BODY,
    EventName.INTENT_TERMINAL: SemanticLane.BODY,
    EventName.MOVEMENT_BLOCKED: SemanticLane.BODY,
    EventName.TACTILE_CONTACT: SemanticLane.BODY,
    EventName.SPEECH_REACH: SemanticLane.NEST,
    EventName.VISUAL_OBSERVATION: SemanticLane.NEST,
    EventName.ENVIRONMENT_STATE: SemanticLane.NEST,
}


class _RuntimeFrame(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    protocol: Literal[3]
    lane: SemanticLane
    message_id: str
    cause_id: Optional[str] = None
    target_actor_id: Optional[str] = None
    runtime_id: str
    generation: int = Field(ge=0)
    world_revision: int = Field(ge=0)
    payload: JsonObject


class RuntimeCommandFrame(_RuntimeFrame):
    """Strict outbound command frame for protocol v3."""

    kind: Literal["command"]
    name: CommandName
    issued_at: datetime

    @model_validator(mode="after")
    def _validate_named_payload(self) -> RuntimeCommandFrame:
        _COMMAND_PAYLOAD_MODELS[self.name].model_validate(self.payload)
        expected_lane = _COMMAND_LANES[self.name]
        if self.lane is not expected_lane:
            raise ValueError(f"{self.name.value} must use {expected_lane.value} lane")
        if self.name is CommandName.CONFIGURE_WORLD:
            if self.payload.get("world_revision") != self.world_revision:
                raise ValueError("configure payload revision must equal frame revision")
        if self.name is CommandName.REQUEST_SPEECH_REACH:
            command_id = self.payload.get("command_id")
            if self.cause_id != command_id:
                raise ValueError("speech reach cause_id must equal command_id")
        if self.name is CommandName.REQUEST_VISUAL_OBSERVATION:
            observation_id = self.payload.get("observation_id")
            if self.cause_id != observation_id:
                raise ValueError(
                    "visual observation cause_id must equal observation_id"
                )
        if self.name is CommandName.APPLY_ENVIRONMENT:
            command_id = self.payload.get("command_id")
            if self.cause_id != command_id:
                raise ValueError("environment cause_id must equal command_id")
        if self.name in {
            CommandName.EXECUTE_INTENT,
            CommandName.CANCEL_INTENT,
        }:
            command_id = self.payload.get("command_id")
            actor_id = self.payload.get("actor_id")
            if self.cause_id != command_id:
                raise ValueError("body command cause_id must equal command_id")
            if self.target_actor_id != actor_id:
                raise ValueError("body command target_actor_id must equal actor_id")
        elif self.target_actor_id is not None:
            raise ValueError("Nest command target_actor_id must be absent")
        return self


class RuntimeEventFrame(_RuntimeFrame):
    """Strict inbound event frame for protocol v3."""

    kind: Literal["event"]
    name: EventName
    occurred_at: datetime

    @model_validator(mode="after")
    def _validate_named_payload(self) -> RuntimeEventFrame:
        _EVENT_PAYLOAD_MODELS[self.name].model_validate(self.payload)
        expected_lane = _EVENT_LANES[self.name]
        if self.lane is not expected_lane:
            raise ValueError(f"{self.name.value} must use {expected_lane.value} lane")
        if self.lane is SemanticLane.BODY:
            actor_id = self.payload.get("actor_id")
            if self.target_actor_id is None:
                raise ValueError("Body event target_actor_id is required")
            if self.target_actor_id != actor_id:
                raise ValueError("Body event target_actor_id must equal actor_id")
        elif self.target_actor_id is not None:
            raise ValueError("non-Body event target_actor_id must be absent")
        if self.name in _COMMAND_CORRELATED_EVENTS:
            correlation_id = self.payload.get(
                "command_id",
                self.payload.get("observation_id"),
            )
            if self.cause_id != correlation_id:
                raise ValueError("command event cause_id must equal correlation id")
        return self


def parse_runtime_command_frame(raw: JsonObject) -> RuntimeCommandFrame:
    """Parse an untrusted outbound command frame into the v3 contract."""
    return RuntimeCommandFrame.model_validate(raw)


def parse_runtime_event_frame(raw: JsonObject) -> RuntimeEventFrame:
    """Parse an untrusted inbound event frame into the v3 contract."""
    return RuntimeEventFrame.model_validate(raw)
