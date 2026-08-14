"""Persistence port for semantic Nest state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from nest.state.models import (
    EnvironmentDesiredState,
    EnvironmentRule,
    PersistentResidentState,
    WorldCatalog,
)


@dataclass(frozen=True)
class NestPersistenceSnapshot:
    """Persistent Nest state restored before a Runtime connects."""

    desired_bed_count: int
    elapsed_seconds: float
    catalog: WorldCatalog | None
    residents: tuple[PersistentResidentState, ...]
    clock_paused: bool = False
    time_scale: float = 1.0
    environment_desired: EnvironmentDesiredState = EnvironmentDesiredState()
    environment_rules: tuple[EnvironmentRule, ...] = ()


class NestPersistenceError(RuntimeError):
    """A semantic Nest persistence mutation could not be committed."""


class NestRepository(Protocol):
    """Repository contract used by orchestration, independent of SQLite."""

    def load_snapshot(self) -> NestPersistenceSnapshot: ...

    def load_home_assignments(self) -> dict[str, PersistentResidentState]: ...

    def save_catalog(self, catalog: WorldCatalog) -> None: ...

    def save_resident(self, resident: PersistentResidentState) -> None: ...

    def remove_resident(self, elfie_id: str) -> None: ...

    def save_time_environment(
        self,
        *,
        elapsed_seconds: float,
        clock_paused: bool,
        time_scale: float,
        environment_desired: EnvironmentDesiredState,
        environment_rules: tuple[EnvironmentRule, ...],
    ) -> None: ...


__all__ = (
    "NestPersistenceError",
    "NestPersistenceSnapshot",
    "NestRepository",
)
