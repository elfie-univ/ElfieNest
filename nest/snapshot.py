"""Technology-neutral durable snapshot owned by the Nest aggregate."""

from __future__ import annotations

from dataclasses import dataclass, field

from nest.config import FIXED_BED_COUNT
from nest.living_rules.models import PersistentResidentState
from nest.space_facilities.models import WorldCatalog
from nest.time_environment.clock import (
    default_environment_desired,
    default_environment_rules,
)
from nest.time_environment.models import EnvironmentDesiredState, EnvironmentRule


@dataclass(frozen=True)
class NestSnapshot:
    """The only durable Nest shape accepted by the application state store."""

    desired_bed_count: int
    elapsed_seconds: float
    catalog: WorldCatalog | None
    residents: tuple[PersistentResidentState, ...]
    clock_paused: bool = False
    time_scale: float = 1.0
    environment_desired: EnvironmentDesiredState = field(
        default_factory=default_environment_desired
    )
    environment_rules: tuple[EnvironmentRule, ...] = field(
        default_factory=default_environment_rules
    )

    def __post_init__(self) -> None:
        if self.desired_bed_count != FIXED_BED_COUNT:
            raise ValueError("desired_bed_count must be fixed at 32")
        if self.elapsed_seconds < 0:
            raise ValueError("elapsed_seconds must be non-negative")
        if self.time_scale <= 0:
            raise ValueError("time_scale must be positive")


__all__ = ("NestSnapshot",)
