"""Typed boundary models for the isolated Nest Lab."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from elfie.profile import ResolvedAppearance
from nest.config import FIXED_BED_COUNT
from nest.public import LifePhase

LabSpecies = Literal["tovren", "saevi"]


class _LabRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LabEnvironmentState(_LabRequest):
    phase: LifePhase
    lights_on: bool
    quiet_mode: bool


class BedCountRequest(_LabRequest):
    """Requested fixed-room bed capacity."""

    bed_count: int = Field(strict=True, ge=FIXED_BED_COUNT, le=FIXED_BED_COUNT)


class CreateActorRequest(_LabRequest):
    """Create and save an experiment Elfie through the shared Lab library."""

    species: LabSpecies
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    age_years: Optional[int] = Field(default=None, strict=True, ge=2, le=100)
    gender: Optional[Literal["male", "female"]] = None


class LabActionRequest(_LabRequest):
    """One manual Lab request using existing Runtime actions."""

    actor_id: str = Field(min_length=1, max_length=128)
    action: Literal["animation", "move", "use"]
    animation: Optional[str] = Field(default=None, min_length=1, max_length=128)
    anchor_id: Optional[str] = Field(default=None, min_length=1, max_length=256)

    furniture_cycle: Optional[
        Literal["seat", "sleep-back", "sleep-left", "sleep-right"]
    ] = None

    @model_validator(mode="after")
    def validate_target(self) -> LabActionRequest:
        if self.action == "animation":
            valid = self.animation is not None and self.anchor_id is None
        else:
            valid = self.anchor_id is not None and self.animation is None
        if self.furniture_cycle is not None and self.action != "use":
            raise ValueError("furniture cycles require a use action")
        if not valid:
            raise ValueError("animation requires a clip; move/use require an anchor")
        return self


@dataclass(frozen=True)
class LabActor:
    """Scene projection of a saved experiment identity and appearance."""

    actor_id: str
    species: LabSpecies
    age_years: int = 4
    gender: Literal["male", "female"] = "female"
    appearance: Optional[ResolvedAppearance] = None
    name: str = ""
    saved: bool = False


@dataclass(frozen=True)
class LabEvent:
    """One observable Lab or Runtime fact for the timeline."""

    sequence: int
    name: str
    detail: str
    occurred_at: str

    def to_dict(self) -> dict[str, str | int]:
        """Return the public timeline representation."""
        return {
            "sequence": self.sequence,
            "name": self.name,
            "detail": self.detail,
            "occurred_at": self.occurred_at,
        }


class NestLabConflictError(RuntimeError):
    """An expected Lab action cannot be applied to current local state."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail
