"""Time and environment semantic value objects."""

from __future__ import annotations

from enum import Enum, unique

from pydantic import BaseModel, ConfigDict, field_validator

from nest.space_facilities.models import (
    DEFAULT_ENVIRONMENT_OBJECT_ID,
    EnvironmentObjectId,
)


class _StrictSemanticModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _require_semantic_id(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("semantic id must not be empty")
    return normalized


@unique
class LifePhase(str, Enum):
    """Stable household phase derived from the Nest clock."""

    NIGHT = "night"
    DAWN = "dawn"
    DAY = "day"
    DUSK = "dusk"


class EnvironmentDesiredState(_StrictSemanticModel):
    """Discrete environment intent owned by Time and Environment."""

    object_id: EnvironmentObjectId = DEFAULT_ENVIRONMENT_OBJECT_ID
    lights_on: bool = True
    quiet_mode: bool = False

    @field_validator("object_id")
    @classmethod
    def _non_empty_object_id(cls, value: str) -> str:
        return _require_semantic_id(value)


class EnvironmentRule(_StrictSemanticModel):
    """One deterministic phase rule for the desired environment."""

    rule_id: str
    phase: LifePhase
    lights_on: bool
    quiet_mode: bool = False

    @field_validator("rule_id")
    @classmethod
    def _non_empty_rule_id(cls, value: str) -> str:
        return _require_semantic_id(value)


__all__ = (
    "EnvironmentDesiredState",
    "EnvironmentObjectId",
    "EnvironmentRule",
    "LifePhase",
)
