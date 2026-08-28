"""Stable Observer workflow errors."""


class ObserverError(RuntimeError):
    """Base error for the scoped Observer workflow."""


class ObserverForbidden(ObserverError):
    """The principal or capability cannot perform the requested operation."""


class ObserverRateLimited(ObserverError):
    """The capability exceeded the existing bounded intent rate."""


class ObserverSessionExpired(ObserverError):
    """The short-lived Observer lease expired and must be reopened."""


class ObserverUnavailable(ObserverError):
    """The existing world projection or intent sink is unavailable."""


__all__ = (
    "ObserverError",
    "ObserverForbidden",
    "ObserverRateLimited",
    "ObserverSessionExpired",
    "ObserverUnavailable",
)
