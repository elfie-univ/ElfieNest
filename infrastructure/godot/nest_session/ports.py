"""Technical Gateway Port consumed by the Nest Session Adapter.

The Gateway implementation is assembled by Bootstrap.  Keeping this narrow
protocol beside the Nest Session Adapter prevents one Infrastructure
capability from constructing another capability's concrete adapter.
"""

from __future__ import annotations

from typing import Protocol

from infrastructure.godot.gateway.messages import (
    CommandName,
    JsonObject,
    RuntimeEventFrame,
)
from infrastructure.godot.gateway.session import (
    RuntimeConnection as GatewayRuntimeConnection,
)


class GatewayRuntimePort(Protocol):
    """Minimal protocol-v2 transport surface needed by Nest Session."""

    @property
    def runtime_connection(self) -> GatewayRuntimeConnection | None: ...

    @property
    def runtime_ready(self) -> bool: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def send_runtime_command(
        self,
        name: CommandName,
        payload: JsonObject,
        *,
        world_revision: int,
        correlation_id: str | None = None,
    ) -> str | None: ...

    def drain_runtime_events(self) -> tuple[RuntimeEventFrame, ...]: ...

    def mark_runtime_ready(
        self,
        connection: GatewayRuntimeConnection,
        *,
        world_revision: int,
    ) -> None: ...

    def send_body_command(
        self,
        payload: dict[str, object],
        *,
        correlation_id: str,
    ) -> bool: ...

    def cancel_body_command(self, *, command_id: str, actor_id: str) -> bool: ...


__all__ = ("GatewayRuntimePort",)
