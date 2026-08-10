"""Technical boundaries consumed by the embodiment workflow."""

from __future__ import annotations

from typing import Protocol

from elfie.body.contracts import BodyCommand, BodySensorEvent, CommandReceipt

from .models import EmbodimentSession


class EmbodimentLeasePortError(RuntimeError):
    """The durable Embodiment boundary could not complete an operation."""


class EmbodimentLeaseConflict(EmbodimentLeasePortError):
    """A durable embodiment transition used stale or conflicting state."""


class EmbodimentLeasePort(Protocol):
    def get(self, elfie_id: str) -> EmbodimentSession: ...

    def list_sessions(self) -> tuple[EmbodimentSession, ...]: ...

    def begin_hosting(
        self, elfie_id: str, body_id: str, *, lease_seconds: float
    ) -> EmbodimentSession: ...

    def complete_hosting(
        self, elfie_id: str, lease_version: int
    ) -> EmbodimentSession: ...

    def abort_hosting(self, elfie_id: str, lease_version: int) -> EmbodimentSession: ...

    def start_return(self, elfie_id: str, lease_version: int) -> EmbodimentSession: ...

    def complete_return(
        self, elfie_id: str, lease_version: int
    ) -> EmbodimentSession: ...

    def heartbeat(
        self, elfie_id: str, lease_version: int, *, lease_seconds: float
    ) -> EmbodimentSession: ...

    def expire(
        self, elfie_id: str, *, now: float | None = None
    ) -> EmbodimentSession: ...

    def recover(self, elfie_id: str, lease_version: int) -> EmbodimentSession: ...


class BodyDeviceGatewayPort(Protocol):
    def connect_device(self, body_id: str) -> None: ...

    def disconnect_device(self, body_id: str) -> None: ...

    def deliver_sensor_event(self, body_id: str, event: BodySensorEvent) -> bool: ...

    def deliver_receipt(self, body_id: str, receipt: CommandReceipt) -> bool: ...

    def drain_commands(self, body_id: str) -> list[BodyCommand]: ...


__all__ = (
    "BodyDeviceGatewayPort",
    "EmbodimentLeaseConflict",
    "EmbodimentLeasePortError",
    "EmbodimentLeasePort",
)
