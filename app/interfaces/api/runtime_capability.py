"""Injected server-side Runtime capability checks for API boundaries."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class RuntimeCapabilityDenied(RuntimeError):
    """A request cannot run at the current Backend/model readiness."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)


@runtime_checkable
class RuntimeCapabilityGate(Protocol):
    """Narrow API-side Port; Bootstrap supplies the lifecycle-backed adapter."""

    def require(self, operation: str) -> None: ...


def require_runtime_capability(application: object, operation: str) -> None:
    """Enforce a capability when production composition supplied a gate.

    Small route tests and offline API fixtures may omit the production lifecycle
    gate. The real Server always injects it, so omitting it is only a test
    composition choice and never a second readiness implementation.
    """
    state = getattr(application, "state", application)
    gate = getattr(state, "runtime_capability_gate", None)
    if gate is None:
        return
    require = getattr(gate, "require", None)
    if not callable(require):
        raise RuntimeCapabilityDenied(
            "CAPABILITY_GATE_UNAVAILABLE",
            "Runtime capability gate is unavailable",
        )
    require(operation)


__all__ = (
    "RuntimeCapabilityDenied",
    "RuntimeCapabilityGate",
    "require_runtime_capability",
)
