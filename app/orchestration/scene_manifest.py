"""Parse Godot semantic scene manifests into the Nest domain catalog."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from nest.godot_gateway.messages import JsonObject
from nest.state.models import (
    AnchorKind,
    InteractionAnchor,
    RuntimeResidentMirror,
    WorldCatalog,
    ZoneDescriptor,
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
    kind: AnchorKind
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


def parse_scene_manifest(payload: JsonObject) -> WorldCatalog:
    """Parse one untrusted flat Godot manifest into nested semantic zones."""
    manifest = _SceneManifest.model_validate(payload)
    anchors_by_zone: dict[str, list[InteractionAnchor]] = {
        zone.zone_id: [] for zone in manifest.zones if zone.active
    }
    for anchor in manifest.anchors:
        if anchor.zone_id not in anchors_by_zone:
            continue
        anchors_by_zone[anchor.zone_id].append(
            InteractionAnchor(
                anchor_id=anchor.anchor_id,
                kind=anchor.kind,
                label=anchor.label,
                order=anchor.stable_order,
                active=anchor.active,
            )
        )
    return WorldCatalog(
        nest_id=manifest.nest_id,
        revision=manifest.world_revision,
        zones=tuple(
            ZoneDescriptor(
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
) -> tuple[int, tuple[RuntimeResidentMirror, ...]]:
    """Parse transient Runtime actor state without persisting coordinates."""
    snapshot = _WorldSnapshot.model_validate(payload)
    return (
        snapshot.world_revision,
        tuple(
            RuntimeResidentMirror(
                elfie_id=actor.actor_id,
                current_zone_id=actor.zone_id,
                posture=actor.posture,
                active_command_id=actor.active_command_id,
            )
            for actor in snapshot.actors
        ),
    )


__all__ = ("parse_scene_manifest", "parse_world_snapshot")
