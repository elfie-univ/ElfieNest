"""Parse Godot semantic scene manifests into the Nest domain catalog."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.orchestration.nest_session import (
    IntentProgress,
    IntentTerminal,
    ResidentMirror,
    RuntimeConnection,
    RuntimeFailure,
    SceneManifest,
    SemanticWorldCatalog,
    SpeechAudience,
    TactileContact,
    WorldAnchor,
    WorldEvent,
    WorldEventName,
    WorldEventPayload,
    WorldReady,
    WorldSnapshot,
    WorldZone,
)
from nest.godot_gateway.messages import EventName, JsonObject, RuntimeEventFrame


class _ManifestZone(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    zone_id: str
    label: str
    stable_order: int = Field(ge=0)
    active: bool


class _ManifestAnchor(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    anchor_id: str
    zone_id: str
    kind: Literal["bed", "chair", "door", "activity"]
    label: str
    stable_order: int = Field(ge=0)
    active: bool


class _SceneManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    nest_id: str
    world_revision: int = Field(ge=0)
    zones: tuple[_ManifestZone, ...]
    anchors: tuple[_ManifestAnchor, ...]


class _SnapshotActor(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    actor_id: str
    zone_id: Optional[str]
    posture: str
    active_command_id: Optional[str]


class _WorldSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    world_revision: int = Field(ge=0)
    actors: tuple[_SnapshotActor, ...]


class _WorldReady(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ready: bool
    navigation_ready: bool = False


class _RuntimeFailure(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    accepted: Optional[bool] = None
    world_revision: Optional[int] = Field(default=None, ge=0)


class _IntentProgress(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: str
    actor_id: str


class _IntentTerminal(_IntentProgress):
    status: Literal["completed", "failed", "cancelled"]
    reason: Optional[str] = None
    detail: Optional[str] = None


class _TactileContact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    actor_id: str
    intensity: float = Field(ge=0.0, le=1.0)
    direction: str
    contact_kind: Literal["actor", "world"]
    source_semantic_id: str


class _SpeechAudience(_IntentProgress):
    text: str
    zone_id: str
    audience_actor_ids: tuple[str, ...]


def parse_scene_manifest(payload: JsonObject) -> SemanticWorldCatalog:
    """Parse one untrusted flat Godot manifest into nested semantic zones."""
    manifest = _SceneManifest.model_validate(payload)
    anchors_by_zone: dict[str, list[WorldAnchor]] = {
        zone.zone_id: [] for zone in manifest.zones if zone.active
    }
    for anchor in manifest.anchors:
        if anchor.zone_id not in anchors_by_zone:
            continue
        anchors_by_zone[anchor.zone_id].append(
            WorldAnchor(
                anchor_id=anchor.anchor_id,
                kind=anchor.kind,
                label=anchor.label,
                order=anchor.stable_order,
                active=anchor.active,
            )
        )
    return SemanticWorldCatalog(
        nest_id=manifest.nest_id,
        revision=manifest.world_revision,
        zones=tuple(
            WorldZone(
                zone_id=zone.zone_id,
                label=zone.label,
                order=zone.stable_order,
                anchors=tuple(anchors_by_zone[zone.zone_id]),
            )
            for zone in manifest.zones
            if zone.active
        ),
    )


def parse_world_snapshot(
    payload: JsonObject,
) -> tuple[int, tuple[ResidentMirror, ...]]:
    """Parse transient Runtime actor state without persisting coordinates."""
    snapshot = _WorldSnapshot.model_validate(payload)
    return (
        snapshot.world_revision,
        tuple(
            ResidentMirror(
                elfie_id=actor.actor_id,
                current_zone_id=actor.zone_id,
                posture=actor.posture,
                active_command_id=actor.active_command_id,
            )
            for actor in snapshot.actors
        ),
    )


def map_runtime_event(frame: RuntimeEventFrame) -> WorldEvent:
    """Translate one validated protocol frame into the App-owned Port model."""
    payload: WorldEventPayload
    if frame.name is EventName.SCENE_MANIFEST:
        payload = SceneManifest(catalog=parse_scene_manifest(frame.payload))
    elif frame.name is EventName.WORLD_SNAPSHOT:
        revision, residents = parse_world_snapshot(frame.payload)
        payload = WorldSnapshot(revision=revision, residents=residents)
    elif frame.name is EventName.WORLD_READY:
        parsed = _WorldReady.model_validate(frame.payload)
        payload = WorldReady(
            ready=parsed.ready,
            navigation_ready=parsed.navigation_ready,
        )
    elif frame.name in {EventName.CONFIG_REJECTED, EventName.STARTUP_ERROR}:
        parsed_failure = _RuntimeFailure.model_validate(frame.payload)
        payload = RuntimeFailure(
            code=parsed_failure.code,
            accepted=parsed_failure.accepted,
        )
    elif frame.name is EventName.INTENT_TERMINAL:
        parsed_terminal = _IntentTerminal.model_validate(frame.payload)
        payload = IntentTerminal(
            command_id=parsed_terminal.command_id,
            actor_id=parsed_terminal.actor_id,
            status=parsed_terminal.status,
            reason=parsed_terminal.reason,
            detail=parsed_terminal.detail,
        )
    elif frame.name in {
        EventName.INTENT_ACCEPTED,
        EventName.INTENT_STARTED,
        EventName.MOVEMENT_BLOCKED,
    }:
        parsed_progress = _IntentProgress.model_validate(frame.payload)
        payload = IntentProgress(
            command_id=parsed_progress.command_id,
            actor_id=parsed_progress.actor_id,
        )
    elif frame.name is EventName.TACTILE_CONTACT:
        parsed_tactile = _TactileContact.model_validate(frame.payload)
        payload = TactileContact(
            actor_id=parsed_tactile.actor_id,
            intensity=parsed_tactile.intensity,
            direction=parsed_tactile.direction,
            contact_kind=parsed_tactile.contact_kind,
            source_semantic_id=parsed_tactile.source_semantic_id,
        )
    elif frame.name is EventName.SPEECH_AUDIENCE:
        parsed_speech = _SpeechAudience.model_validate(frame.payload)
        payload = SpeechAudience(
            command_id=parsed_speech.command_id,
            actor_id=parsed_speech.actor_id,
            text=parsed_speech.text,
            zone_id=parsed_speech.zone_id,
            audience_actor_ids=parsed_speech.audience_actor_ids,
        )
    else:  # pragma: no cover - EventName is closed and every member is mapped above.
        raise ValueError(f"unsupported Runtime event: {frame.name.value}")
    return WorldEvent(
        event_id=frame.message_id,
        connection=RuntimeConnection(
            runtime_id=frame.runtime_id,
            generation=frame.generation,
        ),
        world_revision=frame.world_revision,
        name=WorldEventName(frame.name.value),
        correlation_id=frame.correlation_id,
        payload=payload,
    )


__all__ = ("map_runtime_event", "parse_scene_manifest", "parse_world_snapshot")
