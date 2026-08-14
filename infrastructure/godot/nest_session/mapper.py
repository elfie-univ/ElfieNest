"""Parse Godot semantic scene manifests into the Nest domain catalog."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.orchestration.nest_session import (
    EnvironmentState,
    ResidentMirror,
    RuntimeConnection,
    RuntimeFailure,
    SceneManifest,
    SemanticWorldCatalog,
    SpeechReach,
    VisualObservation,
    WorldAnchor,
    WorldConfigured,
    WorldEvent,
    WorldEventName,
    WorldEventPayload,
    WorldFacility,
    WorldSnapshot,
    WorldZone,
)
from infrastructure.godot.gateway.messages import (
    EventName,
    JsonObject,
    RuntimeEventFrame,
)


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


class _ManifestFacility(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    facility_id: str
    zone_id: str
    kind: Literal["rest", "activity", "transit", "social"]
    label: str
    capabilities: tuple[str, ...] = ()
    active: bool


class _SceneManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    nest_id: str
    world_revision: int = Field(ge=0)
    zones: tuple[_ManifestZone, ...]
    anchors: tuple[_ManifestAnchor, ...]
    facilities: tuple[_ManifestFacility, ...] = ()


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


class _WorldConfigured(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    configured: bool
    navigation_ready: bool = False


class _RuntimeFailure(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    accepted: Optional[bool] = None
    world_revision: Optional[int] = Field(default=None, ge=0)


class _SpeechReach(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: str
    actor_id: str
    zone_id: str
    audience_actor_ids: tuple[str, ...]


class _VisualObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_id: str
    actor_id: str
    zone_id: str
    visible_semantic_ids: tuple[str, ...]


class _EnvironmentState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: str
    lights_on: bool
    quiet_mode: bool
    applied: bool
    reason: Optional[str] = None


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
        facilities=tuple(
            WorldFacility(
                facility_id=facility.facility_id,
                zone_id=facility.zone_id,
                kind=facility.kind,
                label=facility.label,
                capabilities=facility.capabilities,
                active=facility.active,
            )
            for facility in manifest.facilities
            if facility.active and facility.zone_id in anchors_by_zone
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
    elif frame.name is EventName.WORLD_CONFIGURED:
        parsed = _WorldConfigured.model_validate(frame.payload)
        payload = WorldConfigured(
            configured=parsed.configured,
            navigation_ready=parsed.navigation_ready,
        )
    elif frame.name in {EventName.CONFIG_REJECTED, EventName.STARTUP_ERROR}:
        parsed_failure = _RuntimeFailure.model_validate(frame.payload)
        payload = RuntimeFailure(
            code=parsed_failure.code,
            accepted=parsed_failure.accepted,
        )
    elif frame.name is EventName.SPEECH_REACH:
        parsed_speech = _SpeechReach.model_validate(frame.payload)
        payload = SpeechReach(
            command_id=parsed_speech.command_id,
            actor_id=parsed_speech.actor_id,
            zone_id=parsed_speech.zone_id,
            audience_actor_ids=parsed_speech.audience_actor_ids,
        )
    elif frame.name is EventName.VISUAL_OBSERVATION:
        parsed_visual = _VisualObservation.model_validate(frame.payload)
        payload = VisualObservation(
            observation_id=parsed_visual.observation_id,
            actor_id=parsed_visual.actor_id,
            zone_id=parsed_visual.zone_id,
            visible_semantic_ids=parsed_visual.visible_semantic_ids,
        )
    elif frame.name is EventName.ENVIRONMENT_STATE:
        parsed_environment = _EnvironmentState.model_validate(frame.payload)
        payload = EnvironmentState(
            command_id=parsed_environment.command_id,
            lights_on=parsed_environment.lights_on,
            quiet_mode=parsed_environment.quiet_mode,
            applied=parsed_environment.applied,
            reason=parsed_environment.reason,
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
        cause_id=frame.cause_id,
        occurred_at=frame.occurred_at,
        payload=payload,
    )


__all__ = ("map_runtime_event", "parse_scene_manifest", "parse_world_snapshot")
