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
        self.speech_reach_requests: list[tuple[str, str, str, int]] = []
        self.visual_observation_requests: list[tuple[str, str, int, int]] = []
        self.environment_requests: list[tuple[str, bool, bool, int]] = []
        self.configured_revisions: list[int] = []
        self.started = False

    @property
    def runtime_connection(self) -> RuntimeConnection | None:
        return self.connection

    @property
    def runtime_ready(self) -> bool:
        return self.connection is not None

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

    def request_speech_reach(
        self,
        *,
        command_id: str,
        actor_id: str,
        acoustic_profile: str = "normal",
        world_revision: int,
    ) -> str | None:
        if self.connection is None:
            return None
        self.speech_reach_requests.append(
            (command_id, actor_id, acoustic_profile, world_revision)
        )
        return f"speech-reach-{len(self.speech_reach_requests)}"

    def request_visual_observation(
        self,
        *,
        observation_id: str,
        actor_id: str,
        max_results: int = 32,
        world_revision: int,
    ) -> str | None:
        if self.connection is None:
            return None
        self.visual_observation_requests.append(
            (observation_id, actor_id, max_results, world_revision)
        )
        return f"visual-observation-{len(self.visual_observation_requests)}"

    def apply_environment(
        self,
        *,
        command_id: str,
        lights_on: bool,
        quiet_mode: bool,
        world_revision: int,
    ) -> str | None:
        if self.connection is None:
            return None
        self.environment_requests.append(
            (command_id, lights_on, quiet_mode, world_revision)
        )
        return command_id

    def drain_events(self) -> tuple[WorldEvent, ...]:
        drained = tuple(self.events)
        self.events.clear()
        return drained

    def mark_world_configured(
        self,
        connection: RuntimeConnection,
        *,
        world_revision: int,
    ) -> None:
        if connection == self.connection:
            self.configured_revisions.append(world_revision)


__all__ = ("FakeWorldRuntime",)
