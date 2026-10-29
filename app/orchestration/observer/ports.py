"""Outbound Ports consumed by the Observer workflow."""

from __future__ import annotations

from typing import Protocol

from .port_models import (
    ObserverEntityRecord,
    ObserverEnvironmentRecord,
    ObserverWorldIntent,
)


class ObserverPortError(RuntimeError):
    """A technical Observer adapter could not serve the workflow."""


class ObserverWorldPort(Protocol):
    def read_environment(self) -> ObserverEnvironmentRecord | None: ...

    def list_entities(self) -> tuple[ObserverEntityRecord, ...]: ...

    def submit_intent(self, intent: ObserverWorldIntent) -> None: ...


class ObserverClockPort(Protocol):
    def now(self) -> float: ...


class ObserverCapabilityIssuerPort(Protocol):
    def issue(self) -> str: ...


__all__ = (
    "ObserverCapabilityIssuerPort",
    "ObserverClockPort",
    "ObserverPortError",
    "ObserverWorldPort",
)
