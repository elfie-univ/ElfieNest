"""Stable errors raised by external-body use-cases."""


class BodiesError(RuntimeError):
    """Base error for the external-bodies Feature."""


class BodiesForbidden(BodiesError):
    """The principal cannot administer external bodies."""


class BodyNotFound(BodiesError):
    """The requested Elfie/body association does not exist."""


class BodyConflict(BodiesError):
    """The requested body mutation conflicts with its active state."""


class BodyCredentialRejected(BodiesError):
    """The supplied independent body credential is invalid or revoked."""


class BodyInputInvalid(BodiesError):
    """The requested body mutation is malformed."""


class BodiesUnavailable(BodiesError):
    """The body authority could not complete the operation."""


__all__ = (
    "BodiesError",
    "BodiesForbidden",
    "BodiesUnavailable",
    "BodyConflict",
    "BodyCredentialRejected",
    "BodyInputInvalid",
    "BodyNotFound",
)
