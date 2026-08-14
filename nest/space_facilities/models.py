"""Nest 内部状态值对象。"""

from __future__ import annotations

from enum import Enum, unique
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import TypeAlias

AnchorId: TypeAlias = str
FacilityId: TypeAlias = str
NestId: TypeAlias = str
WorldRevision: TypeAlias = int
ZoneId: TypeAlias = str
EnvironmentObjectId: TypeAlias = str

# The first supported environment object is an aggregate owned by the Nest
# scene.  Keeping one stable ID makes desired commands and Runtime facts
# addressable without pretending that Python owns individual Light3D nodes.
DEFAULT_ENVIRONMENT_OBJECT_ID = "nest/environment"


@unique
class AnchorKind(str, Enum):
    """Godot Runtime 暴露给 Nest 的封闭交互锚点类型。"""

    BED = "bed"
    CHAIR = "chair"
    DOOR = "door"
    ACTIVITY = "activity"


@unique
class FacilityKind(str, Enum):
    """Household-facing purpose of a stable physical facility."""

    REST = "rest"
    ACTIVITY = "activity"
    TRANSIT = "transit"
    SOCIAL = "social"


class _StrictSemanticModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _require_semantic_id(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        msg = "semantic id must not be empty"
        raise ValueError(msg)
    return normalized


class InteractionAnchor(_StrictSemanticModel):
    """Runtime scene manifest 中的稳定语义交互点。"""

    anchor_id: AnchorId
    kind: AnchorKind
    label: str
    order: int = Field(ge=0)
    active: bool = True

    @field_validator("anchor_id", "label")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        return _require_semantic_id(value)


class ZoneDescriptor(_StrictSemanticModel):
    """Runtime scene manifest 中的稳定语义区域。"""

    zone_id: ZoneId
    label: str
    order: int = Field(ge=0)
    anchors: tuple[InteractionAnchor, ...] = ()

    @field_validator("zone_id", "label")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        return _require_semantic_id(value)


class FacilityDescriptor(_StrictSemanticModel):
    """Coordinate-free facility meaning published by the Runtime."""

    facility_id: FacilityId
    zone_id: ZoneId
    kind: FacilityKind
    label: str
    capabilities: tuple[str, ...] = ()
    active: bool = True

    @field_validator("facility_id", "zone_id", "label")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        return _require_semantic_id(value)

    @field_validator("capabilities")
    @classmethod
    def _capabilities_are_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_require_semantic_id(item) for item in value)
        if len(set(normalized)) != len(normalized):
            raise ValueError("facility capabilities must be unique")
        return normalized


class WorldCatalog(_StrictSemanticModel):
    """Godot Runtime 发布给 Nest 的无坐标世界目录。"""

    nest_id: NestId
    revision: WorldRevision = Field(ge=0)
    zones: tuple[ZoneDescriptor, ...]
    facilities: tuple[FacilityDescriptor, ...] = ()

    @field_validator("nest_id")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        return _require_semantic_id(value)

    @model_validator(mode="after")
    def _anchor_ids_are_unique(self) -> WorldCatalog:
        seen: set[AnchorId] = set()
        for zone in self.zones:
            for anchor in zone.anchors:
                if anchor.anchor_id in seen:
                    msg = f"duplicate anchor_id: {anchor.anchor_id}"
                    raise ValueError(msg)
                seen.add(anchor.anchor_id)
        return self

    @model_validator(mode="after")
    def _facility_ids_and_zones_are_valid(self) -> WorldCatalog:
        zone_ids = {zone.zone_id for zone in self.zones}
        seen: set[FacilityId] = set()
        for facility in self.facilities:
            if facility.facility_id in seen:
                raise ValueError(f"duplicate facility_id: {facility.facility_id}")
            if facility.zone_id not in zone_ids:
                raise ValueError(
                    f"facility references unknown zone: {facility.zone_id}"
                )
            seen.add(facility.facility_id)
        return self

    @property
    def anchor_ids(self) -> frozenset[AnchorId]:
        return frozenset(
            anchor.anchor_id for zone in self.zones for anchor in zone.anchors
        )

    @property
    def facility_ids(self) -> frozenset[FacilityId]:
        return frozenset(facility.facility_id for facility in self.facilities)


class EnvironmentActualState(_StrictSemanticModel):
    """Last discrete environment fact acknowledged by the Runtime."""

    object_id: EnvironmentObjectId = DEFAULT_ENVIRONMENT_OBJECT_ID
    command_id: str
    lights_on: bool
    quiet_mode: bool
    applied: bool
    reason: Optional[str] = None
    runtime_id: str
    runtime_generation: int = Field(ge=1)
    world_revision: WorldRevision = Field(ge=1)

    @field_validator("object_id", "command_id", "runtime_id")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        return _require_semantic_id(value)


__all__ = (
    "AnchorId",
    "AnchorKind",
    "DEFAULT_ENVIRONMENT_OBJECT_ID",
    "EnvironmentActualState",
    "EnvironmentObjectId",
    "FacilityDescriptor",
    "FacilityId",
    "FacilityKind",
    "InteractionAnchor",
    "NestId",
    "WorldCatalog",
    "WorldRevision",
    "ZoneDescriptor",
    "ZoneId",
)
