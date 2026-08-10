"""Business errors exposed by the Embodiment workflow."""

from __future__ import annotations


class EmbodimentError(RuntimeError):
    """Base error for an Embodiment use case."""


class EmbodimentForbidden(EmbodimentError):
    """The principal cannot read the requested Embodiment projection."""


class EmbodimentUnavailable(EmbodimentError):
    """The durable Embodiment projection is unavailable."""


__all__ = ("EmbodimentError", "EmbodimentForbidden", "EmbodimentUnavailable")
