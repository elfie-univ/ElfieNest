"""Typed models crossing the Nest Session world-runtime boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum, unique
from typing import Literal, Union

from pydantic import JsonValue

Appearance = Mapping[str, JsonValue]


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
    """One resident in a complete desired actor synchronization."""

    actor_id: str
    species: str
    appearance: Appearance
    home_anchor_id: str


@unique
class WorldEventName(str, Enum):
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


@dataclass(frozen=True)
class WorldReady:
    ready: bool
    navigation_ready: bool


@dataclass(frozen=True)
class WorldAnchor:
    anchor_id: str
    kind: Literal["bed", "chair", "door", "activity"]
    label: str
    order: int
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


@dataclass(frozen=True)
class SceneManifest:
    catalog: SemanticWorldCatalog


@dataclass(frozen=True)
class ResidentMirror:
    elfie_id: str
    current_zone_id: str | None
    posture: str
    active_command_id: str | None = None


@dataclass(frozen=True)
class WorldSnapshot:
    revision: int
    residents: tuple[ResidentMirror, ...]


@dataclass(frozen=True)
class RuntimeFailure:
    code: str
    accepted: bool | None = None


@dataclass(frozen=True)
class IntentProgress:
    command_id: str
    actor_id: str


@dataclass(frozen=True)
class IntentTerminal:
    command_id: str
    actor_id: str
    status: Literal["completed", "failed", "cancelled"]
    reason: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class TactileContact:
    actor_id: str
    intensity: float
    direction: str
    contact_kind: Literal["actor", "world"]
    source_semantic_id: str


@dataclass(frozen=True)
class SpeechAudience:
    command_id: str
    actor_id: str
    text: str
    zone_id: str
    audience_actor_ids: tuple[str, ...]


WorldEventPayload = Union[
    WorldReady,
    SceneManifest,
    WorldSnapshot,
    RuntimeFailure,
    IntentProgress,
    IntentTerminal,
    TactileContact,
    SpeechAudience,
]


@dataclass(frozen=True)
class WorldEvent:
    """Transport-free semantic event delivered by the Godot Adapter."""

    event_id: str
    connection: RuntimeConnection
    world_revision: int
    name: WorldEventName
    payload: WorldEventPayload
    correlation_id: str | None = None


__all__ = (
    "ActorDescriptor",
    "Appearance",
    "IntentProgress",
    "IntentTerminal",
    "RuntimeActor",
    "RuntimeConnection",
    "RuntimeFailure",
    "ResidentMirror",
    "SceneManifest",
    "SemanticWorldCatalog",
    "SpeechAudience",
    "TactileContact",
    "WorldEvent",
    "WorldEventName",
    "WorldEventPayload",
    "WorldAnchor",
    "WorldReady",
    "WorldSnapshot",
    "WorldZone",
)
