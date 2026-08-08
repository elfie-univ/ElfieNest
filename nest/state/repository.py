"""Persistence port for semantic Nest state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from nest.state.models import PersistentResidentState, WorldCatalog


@dataclass(frozen=True)
class NestPersistenceSnapshot:
    """Persistent Nest state restored before a Runtime connects."""

    desired_bed_count: int
    elapsed_seconds: float
    catalog: WorldCatalog | None
    residents: tuple[PersistentResidentState, ...]


class NestPersistenceError(RuntimeError):
    """A semantic Nest persistence mutation could not be committed."""


class NestRepository(Protocol):
    """Repository contract used by orchestration, independent of SQLite."""

    def load_snapshot(self) -> NestPersistenceSnapshot: ...

    def load_home_assignments(self) -> dict[str, PersistentResidentState]: ...

    def save_catalog(self, catalog: WorldCatalog) -> None: ...

    def save_resident(self, resident: PersistentResidentState) -> None: ...

    def remove_resident(self, elfie_id: str) -> None: ...


__all__ = (
    "NestPersistenceError",
    "NestPersistenceSnapshot",
    "NestRepository",
)
