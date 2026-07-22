"""Typed failures for the single-Elfie lifecycle facade."""

from dataclasses import dataclass


@dataclass(frozen=True)  # noqa: SLOTS_OK - Python 3.9
class ElfieLifecycleError(RuntimeError):
    """A lifecycle operation conflicts with the assembled Elfie runtime."""

    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True)  # noqa: SLOTS_OK - Python 3.9
class InvalidClockDeltaError(ValueError):
    """Simulation time cannot move backwards."""

    seconds: float

    def __str__(self) -> str:
        return f"clock delta cannot be negative: {self.seconds}"


__all__ = ("ElfieLifecycleError", "InvalidClockDeltaError")
