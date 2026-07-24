"""Nest 内部状态值对象。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, unique
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import TypeAlias

AnchorId: TypeAlias = str
NestId: TypeAlias = str
WorldRevision: TypeAlias = int
ZoneId: TypeAlias = str


@unique
class AnchorKind(str, Enum):
    """Godot Runtime 暴露给 Nest 的封闭交互锚点类型。"""

    BED = "bed"
    CHAIR = "chair"
    DOOR = "door"
    ACTIVITY = "activity"


@unique
class ResidentPresence(str, Enum):
    """居民在 Nest 语义状态中的长期 presence。"""

    ACTIVE = "active"
    AWAY = "away"
    PENDING_RUNTIME = "pending_runtime"


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


class WorldCatalog(_StrictSemanticModel):
    """Godot Runtime 发布给 Nest 的无坐标世界目录。"""

    nest_id: NestId
    revision: WorldRevision = Field(ge=0)
    zones: tuple[ZoneDescriptor, ...]

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

    @property
    def anchor_ids(self) -> frozenset[AnchorId]:
        return frozenset(
            anchor.anchor_id for zone in self.zones for anchor in zone.anchors
        )


class PersistentResidentState(_StrictSemanticModel):
    """可持久化的居民 Nest 语义状态。"""

    elfie_id: str
    presence: ResidentPresence
    home_zone_id: Optional[ZoneId] = None
    home_anchor_id: Optional[AnchorId] = None

    @field_validator("elfie_id")
    @classmethod
    def _non_empty_elfie_id(cls, value: str) -> str:
        return _require_semantic_id(value)


class HomeAssignment(_StrictSemanticModel):
    """居民长期住处，只能绑定到 bed anchor。"""

    elfie_id: str
    home_zone_id: ZoneId
    home_anchor_id: AnchorId
    anchor_kind: AnchorKind

    @field_validator("elfie_id", "home_zone_id", "home_anchor_id")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        return _require_semantic_id(value)

    @model_validator(mode="after")
    def _requires_bed_anchor(self) -> HomeAssignment:
        if self.anchor_kind is not AnchorKind.BED:
            msg = "home assignment requires bed anchor"
            raise ValueError(msg)
        return self


class RuntimeResidentMirror(_StrictSemanticModel):
    """Runtime 回传的居民临时镜像，不进入长期持久状态。"""

    elfie_id: str
    current_zone_id: Optional[ZoneId] = None
    posture: str = "standing"
    active_command_id: Optional[str] = None

    @field_validator("elfie_id", "posture")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        return _require_semantic_id(value)


@dataclass(frozen=True)
class ResidentState:
    """精灵进入 Nest 后的空间语义状态。"""

    elfie_id: str
    posture: str = "standing"
    active: bool = True
