"""Household membership, home and resident projection value objects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, unique
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import TypeAlias

from nest.space_facilities.models import AnchorId, AnchorKind, WorldRevision, ZoneId

ElfieId: TypeAlias = str


class _StrictSemanticModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _require_semantic_id(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("semantic id must not be empty")
    return normalized


@unique
class ResidentPresence(str, Enum):
    """Long-lived household presence of a resident."""

    ACTIVE = "active"
    AWAY = "away"
    PENDING_RUNTIME = "pending_runtime"


class PersistentResidentState(_StrictSemanticModel):
    """Durable resident meaning owned by Household Living Rules."""

    elfie_id: ElfieId
    presence: ResidentPresence
    home_zone_id: Optional[ZoneId] = None
    home_anchor_id: Optional[AnchorId] = None

    @field_validator("elfie_id")
    @classmethod
    def _non_empty_elfie_id(cls, value: str) -> str:
        return _require_semantic_id(value)


class HomeAssignment(_StrictSemanticModel):
    """A resident's long-lived home, restricted to a bed anchor."""

    elfie_id: ElfieId
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
            raise ValueError("home assignment requires bed anchor")
        return self


class RuntimeResidentMirror(_StrictSemanticModel):
    """Short-lived Runtime projection of a registered resident."""

    elfie_id: ElfieId
    current_zone_id: Optional[ZoneId] = None
    posture: str = "standing"
    active_command_id: Optional[str] = None
    runtime_id: str
    runtime_generation: int = Field(ge=1)
    world_revision: WorldRevision = Field(ge=1)

    @field_validator("elfie_id", "posture", "runtime_id")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        return _require_semantic_id(value)


@dataclass(frozen=True)
class ResidentState:
    """Mutable in-memory resident state held by Household Living Rules."""

    elfie_id: str
    posture: str = "standing"
    active: bool = True


__all__ = (
    "ElfieId",
    "HomeAssignment",
    "PersistentResidentState",
    "ResidentPresence",
    "ResidentState",
    "RuntimeResidentMirror",
)
