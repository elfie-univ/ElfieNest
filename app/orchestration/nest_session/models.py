"""Typed models crossing the Nest Session world-runtime boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, unique
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, JsonValue

Appearance = Mapping[str, JsonValue]


class RuntimeMockMotion(BaseModel):
    """Transient App projection of the removable visual Mock motion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    waypoint: int = Field(ge=0, le=5)
    sequence: int = Field(ge=1)


class ObserverSemanticEntity(BaseModel):
    """Geometry-free Nest facts exposed to the Observer adapter."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    room_id: str = Field(default="local-nest", min_length=1)
    zone_id: Optional[str] = None
    posture: str = Field(default="standing", min_length=1)
    active: bool = True
    active_command_id: Optional[str] = None
    species_id: Optional[str] = None
    appearance: dict[str, JsonValue] = Field(default_factory=dict)
    home_anchor_id: Optional[str] = None
    mock_motion: Optional[RuntimeMockMotion] = None


@dataclass(frozen=True)
class RuntimeConnection:
    """Identity of the currently authoritative Runtime generation."""

    runtime_id: str
    generation: int


@dataclass(frozen=True)
class ActorDescriptor:
    """Render-stable actor identity supplied to the world authority."""

    actor_id: str
    species: str
    appearance: Appearance


@dataclass(frozen=True)
class RuntimeActor:
    """One resident plus a resolved physical spawn target for Godot."""

    actor_id: str
    species: str
    appearance: Appearance
    spawn_anchor_id: str


@unique
class WorldEventName(str, Enum):
    WORLD_CONFIGURED = "world_configured"
    SCENE_MANIFEST = "scene_manifest"
    WORLD_SNAPSHOT = "world_snapshot"
    CONFIG_REJECTED = "config_rejected"
    STARTUP_ERROR = "startup_error"
    SPEECH_REACH = "speech_reach"
    VISUAL_OBSERVATION = "visual_observation"
    ENVIRONMENT_STATE = "environment_state"


@dataclass(frozen=True)
class WorldConfigured:
    configured: bool
    navigation_ready: bool


@dataclass(frozen=True)
class WorldAnchor:
    anchor_id: str
    kind: Literal["bed", "chair", "door", "activity"]
    label: str
    order: int
    active: bool


@dataclass(frozen=True)
class WorldFacility:
    facility_id: str
    zone_id: str
    kind: Literal["rest", "activity", "transit", "social"]
    label: str
    capabilities: tuple[str, ...]
    active: bool


@dataclass(frozen=True)
class WorldZone:
    zone_id: str
    label: str
    order: int
    anchors: tuple[WorldAnchor, ...]


@dataclass(frozen=True)
class SemanticWorldCatalog:
    nest_id: str
    revision: int
    zones: tuple[WorldZone, ...]
    facilities: tuple[WorldFacility, ...] = ()


@dataclass(frozen=True)
class SceneManifest:
    catalog: SemanticWorldCatalog


@dataclass(frozen=True)
class ResidentMirror:
    elfie_id: str
    current_zone_id: str | None
    posture: str
    active_command_id: str | None = None
    mock_motion: RuntimeMockMotion | None = None
    position: tuple[float, float, float] | None = None
    heading_degrees: float | None = None
    velocity: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class WorldSnapshot:
    revision: int
    residents: tuple[ResidentMirror, ...]


@dataclass(frozen=True)
class RuntimeFailure:
    code: str
    accepted: bool | None = None


@dataclass(frozen=True)
class SpeechReach:
    command_id: str
    actor_id: str
    zone_id: str
    audience_actor_ids: tuple[str, ...]


@dataclass(frozen=True)
class VisualObservation:
    observation_id: str
    actor_id: str
    zone_id: str
    visible_semantic_ids: tuple[str, ...]


@dataclass(frozen=True)
class EnvironmentState:
    object_id: str
    command_id: str
    lights_on: bool
    quiet_mode: bool
    applied: bool
    reason: str | None = None


WorldEventPayload = Union[
    WorldConfigured,
    SceneManifest,
    WorldSnapshot,
    RuntimeFailure,
    SpeechReach,
    VisualObservation,
    EnvironmentState,
]


@dataclass(frozen=True)
class WorldEvent:
    """Transport-free semantic event delivered by the Godot Adapter."""

    event_id: str
    connection: RuntimeConnection
    world_revision: int
    name: WorldEventName
    payload: WorldEventPayload
    cause_id: str | None = None
    occurred_at: datetime | None = None


__all__ = (
    "ActorDescriptor",
    "Appearance",
    "ObserverSemanticEntity",
    "RuntimeActor",
    "RuntimeConnection",
    "RuntimeFailure",
    "RuntimeMockMotion",
    "ResidentMirror",
    "SceneManifest",
    "SemanticWorldCatalog",
    "SpeechReach",
    "VisualObservation",
    "EnvironmentState",
    "WorldEvent",
    "WorldEventName",
    "WorldEventPayload",
    "WorldAnchor",
    "WorldFacility",
    "WorldConfigured",
    "WorldSnapshot",
    "WorldZone",
)
