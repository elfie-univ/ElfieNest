"""Stable workflow errors for one live Nest Session."""


class NestSessionLifecycleError(RuntimeError):
    """A Nest Session operation conflicts with its active lifecycle state."""


__all__ = ("NestSessionLifecycleError",)
