"""Godot protocol Adapter for the live Nest Session world Port."""

from __future__ import annotations

from app.orchestration.nest_session import (
    RuntimeActor,
    RuntimeConnection,
    WorldEvent,
)
from elfie.body.native.godot_transport import RuntimeIntentPayload
from infrastructure.godot.gateway.api import GodotAPIServer
from infrastructure.godot.gateway.messages import CommandName
from infrastructure.godot.nest_session.mapper import map_runtime_event


class GodotNestSessionAdapter:
    """Translate semantic world operations to the Godot protocol v2 gateway."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        http_port: int = 8000,
        gateway: GodotAPIServer | None = None,
    ) -> None:
        self._gateway = gateway or GodotAPIServer(
            host=host,
            port=port,
            http_port=http_port,
        )

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
                        "home_anchor_id": actor.home_anchor_id,
                    }
                    for actor in actors
                ]
            },
            world_revision=world_revision,
        )

    def drain_events(self) -> tuple[WorldEvent, ...]:
        return tuple(
            map_runtime_event(frame) for frame in self._gateway.drain_runtime_events()
        )

    def mark_ready(
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
        self._gateway.mark_runtime_ready(active, world_revision=world_revision)

    def send_body_command(
        self,
        payload: RuntimeIntentPayload,
        *,
        correlation_id: str,
    ) -> bool:
        return self._gateway.send_body_command(
            dict(payload),
            correlation_id=correlation_id,
        )

    def cancel_body_command(self, *, command_id: str, actor_id: str) -> bool:
        return self._gateway.cancel_body_command(
            command_id=command_id,
            actor_id=actor_id,
        )


__all__ = ("GodotNestSessionAdapter",)
