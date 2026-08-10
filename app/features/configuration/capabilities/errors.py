"""Stable business errors for global capability configuration."""

from __future__ import annotations


class CapabilitiesError(RuntimeError):
    """Base class for expected capability-administration failures."""


class CapabilitiesForbidden(CapabilitiesError):
    """The principal cannot administer global capabilities."""


class CapabilitiesValidationError(CapabilitiesError):
    """A capability mutation violates an existing product constraint."""


class CapabilitiesUnavailable(CapabilitiesError):
    """The authoritative capability boundary is unavailable."""


__all__ = (
    "CapabilitiesError",
    "CapabilitiesForbidden",
    "CapabilitiesUnavailable",
    "CapabilitiesValidationError",
)
