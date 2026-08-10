"""Outbound ports owned by the live Nest Session workflow."""

from __future__ import annotations

from typing import Protocol

from app.orchestration.nest_session.models import (
    RuntimeActor,
    RuntimeConnection,
    WorldEvent,
)
from elfie.brain.runtime_port import CorticalRuntimePort


class CorticalRuntimeFactory(Protocol):
    """Create the already-configured cognition boundary for one real Elfie."""

    def __call__(self, elfie_id: str) -> CorticalRuntimePort: ...


class WorldRuntimePort(Protocol):
    """Semantic world channel required by the Nest tick workflow."""

    @property
    def runtime_connection(self) -> RuntimeConnection | None: ...

    @property
    def runtime_ready(self) -> bool: ...

    def configure_world(
        self,
        *,
        nest_id: str,
        bed_count: int,
        world_revision: int,
    ) -> str | None: ...

    def synchronize_actors(
        self,
        actors: tuple[RuntimeActor, ...],
        *,
        world_revision: int,
    ) -> str | None: ...

    def drain_events(self) -> tuple[WorldEvent, ...]: ...

    def mark_ready(
        self,
        connection: RuntimeConnection,
        *,
        world_revision: int,
    ) -> None: ...


__all__ = ("CorticalRuntimeFactory", "WorldRuntimePort")
