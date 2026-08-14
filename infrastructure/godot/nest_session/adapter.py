"""Godot protocol Adapter for the live Nest Session world Port."""

from __future__ import annotations

from app.orchestration.nest_session import (
    RuntimeActor,
    RuntimeConnection,
    WorldEvent,
)
from infrastructure.godot.body_transport import RuntimeIntentPayload
from infrastructure.godot.gateway.messages import CommandName
from infrastructure.godot.nest_session.mapper import map_runtime_event
from infrastructure.godot.nest_session.ports import BodyEventSink, GatewayRuntimePort


class GodotNestSessionAdapter:
    """Translate semantic world operations to the Godot protocol v3 gateway."""

    def __init__(
        self,
        *,
        gateway: GatewayRuntimePort,
    ) -> None:
        self._gateway = gateway

    def start(self) -> None:
        self._gateway.start()

    def stop(self) -> None:
        self._gateway.stop()

    @property
    def runtime_connection(self) -> RuntimeConnection | None:
        connection = self._gateway.runtime_connection
        if connection is None:
            return None
        return RuntimeConnection(
            runtime_id=connection.runtime_id,
            generation=connection.generation,
        )

    @property
    def runtime_ready(self) -> bool:
        return self._gateway.runtime_ready

    def configure_world(
        self,
        *,
        nest_id: str,
        bed_count: int,
        world_revision: int,
    ) -> str | None:
        return self._gateway.send_runtime_command(
            CommandName.CONFIGURE_WORLD,
            {
                "nest_id": nest_id,
                "bed_count": bed_count,
                "world_revision": world_revision,
            },
            world_revision=world_revision,
        )

    def synchronize_actors(
        self,
        actors: tuple[RuntimeActor, ...],
        *,
        world_revision: int,
    ) -> str | None:
        return self._gateway.send_runtime_command(
            CommandName.SYNC_ACTORS,
            {
                "actors": [
                    {
                        "actor_id": actor.actor_id,
                        "species": actor.species,
                        "appearance": dict(actor.appearance),
                        "spawn_anchor_id": actor.spawn_anchor_id,
                    }
                    for actor in actors
                ]
            },
            world_revision=world_revision,
        )

    def request_speech_reach(
        self,
        *,
        command_id: str,
        actor_id: str,
        acoustic_profile: str = "normal",
        world_revision: int,
    ) -> str | None:
        return self._gateway.send_runtime_command(
            CommandName.REQUEST_SPEECH_REACH,
            {
                "command_id": command_id,
                "actor_id": actor_id,
                "acoustic_profile": acoustic_profile,
            },
            world_revision=world_revision,
            cause_id=command_id,
        )

    def request_visual_observation(
        self,
        *,
        observation_id: str,
        actor_id: str,
        max_results: int = 32,
        world_revision: int,
    ) -> str | None:
        return self._gateway.send_runtime_command(
            CommandName.REQUEST_VISUAL_OBSERVATION,
            {
                "observation_id": observation_id,
                "actor_id": actor_id,
                "max_results": max_results,
            },
            world_revision=world_revision,
            cause_id=observation_id,
        )

    def apply_environment(
        self,
        *,
        command_id: str,
        lights_on: bool,
        quiet_mode: bool,
        world_revision: int,
    ) -> str | None:
        return self._gateway.send_runtime_command(
            CommandName.APPLY_ENVIRONMENT,
            {
                "command_id": command_id,
                "lights_on": lights_on,
                "quiet_mode": quiet_mode,
            },
            world_revision=world_revision,
            cause_id=command_id,
        )

    def drain_events(self) -> tuple[WorldEvent, ...]:
        return tuple(
            map_runtime_event(frame) for frame in self._gateway.drain_runtime_events()
        )

    def mark_world_configured(
        self,
        connection: RuntimeConnection,
        *,
        world_revision: int,
    ) -> None:
        active = self._gateway.runtime_connection
        if (
            active is None
            or active.runtime_id != connection.runtime_id
            or active.generation != connection.generation
        ):
            return
        self._gateway.mark_world_configured(active, world_revision=world_revision)

    def register_body_sink(self, actor_id: str, sink: BodyEventSink) -> None:
        self._gateway.register_body_sink(actor_id, sink)

    def unregister_body_sink(self, actor_id: str, sink: BodyEventSink) -> None:
        self._gateway.unregister_body_sink(actor_id, sink)

    def send_body_command(
        self,
        payload: RuntimeIntentPayload,
        *,
        cause_id: str,
    ) -> bool:
        return self._gateway.send_body_command(
            payload,
            cause_id=cause_id,
        )

    def cancel_body_command(self, *, command_id: str, actor_id: str) -> bool:
        return self._gateway.cancel_body_command(
            command_id=command_id,
            actor_id=actor_id,
        )


__all__ = ("GodotNestSessionAdapter",)
