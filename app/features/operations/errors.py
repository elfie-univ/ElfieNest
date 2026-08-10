"""Stable business errors raised by the Operations facade."""


class OperationsError(RuntimeError):
    """Base class for Operations use-case failures."""


class OperationsForbidden(OperationsError):
    """The authenticated principal cannot read management projections."""


class OperationsUnavailable(OperationsError):
    """An Operations fact source is unavailable."""


class DatabaseMaintenanceRejected(OperationsError):
    """A destructive database target failed the existing safety policy."""


__all__ = (
    "DatabaseMaintenanceRejected",
    "OperationsError",
    "OperationsForbidden",
    "OperationsUnavailable",
)
