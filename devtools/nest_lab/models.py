"""Typed boundary models for the isolated Nest Lab."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LabSpecies = Literal["dog", "fox"]


class _LabRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class BedCountRequest(_LabRequest):
    """Requested fixed-room bed capacity."""

    bed_count: int = Field(ge=1, le=32)


class CreateActorRequest(_LabRequest):
    """A developer request to add one temporary rendered actor."""

    species: LabSpecies


@dataclass(frozen=True)
class LabActor:
    """Temporary actor identity owned by the Lab controller."""

    actor_id: str
    species: LabSpecies


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
