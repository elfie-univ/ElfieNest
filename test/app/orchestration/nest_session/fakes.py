from __future__ import annotations

from app.orchestration.nest_session import (
    RuntimeActor,
    RuntimeConnection,
    WorldEvent,
)


class FakeWorldRuntime:
    def __init__(self) -> None:
        self.connection: RuntimeConnection | None = None
        self.events: list[WorldEvent] = []
        self.configurations: list[tuple[str, int, int]] = []
        self.actor_syncs: list[tuple[tuple[RuntimeActor, ...], int]] = []
        self.ready_revisions: list[int] = []
        self.started = False

    @property
    def runtime_connection(self) -> RuntimeConnection | None:
        return self.connection

    @property
    def runtime_ready(self) -> bool:
        return bool(self.ready_revisions)

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def configure_world(
        self,
        *,
        nest_id: str,
        bed_count: int,
        world_revision: int,
    ) -> str | None:
        if self.connection is None:
            return None
        self.configurations.append((nest_id, bed_count, world_revision))
        return f"configure-{len(self.configurations)}"

    def synchronize_actors(
        self,
        actors: tuple[RuntimeActor, ...],
        *,
        world_revision: int,
    ) -> str | None:
        if self.connection is None:
            return None
        self.actor_syncs.append((actors, world_revision))
        return f"sync-{len(self.actor_syncs)}"

    def drain_events(self) -> tuple[WorldEvent, ...]:
        drained = tuple(self.events)
        self.events.clear()
        return drained

    def mark_ready(
        self,
        connection: RuntimeConnection,
        *,
        world_revision: int,
    ) -> None:
        if connection == self.connection:
            self.ready_revisions.append(world_revision)


__all__ = ("FakeWorldRuntime",)
