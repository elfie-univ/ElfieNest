"""Narrow protocol used by orchestration to control one Godot Runtime."""

from __future__ import annotations

from typing import Protocol

from nest.godot.messages import CommandName, JsonObject, RuntimeEventFrame
from nest.godot.session import RuntimeConnection


class RuntimeGateway(Protocol):
    """Thread-safe command/event boundary exposed to the Nest tick loop."""

    def start(self) -> None: ...

    def stop(self) -> None: ...

    @property
    def runtime_connection(self) -> RuntimeConnection | None: ...

    def mark_runtime_ready(
        self,
        connection: RuntimeConnection,
        *,
        world_revision: int,
    ) -> None: ...

    def send_runtime_command(
        self,
        name: CommandName,
        payload: JsonObject,
        *,
        world_revision: int,
        correlation_id: str | None = None,
    ) -> str | None: ...

    def drain_runtime_events(self) -> tuple[RuntimeEventFrame, ...]: ...


__all__ = ("RuntimeGateway",)
