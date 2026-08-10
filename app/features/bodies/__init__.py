"""Public external-body Feature boundary."""

from .errors import (
    BodiesError,
    BodiesForbidden,
    BodiesUnavailable,
    BodyConflict,
    BodyCredentialRejected,
    BodyInputInvalid,
    BodyNotFound,
)
from .models import (
    AuthenticateBodyCommand,
    BodyCredentialResult,
    BodyPrincipal,
    BodyResult,
    EnrollBodyCommand,
    ListBodiesQuery,
    RecordBodyActivityCommand,
    RevokeBodyCommand,
    RotateBodyCredentialCommand,
)
from .service import BodiesService

__all__ = (
    "AuthenticateBodyCommand",
    "BodiesError",
    "BodiesForbidden",
    "BodiesService",
    "BodiesUnavailable",
    "BodyConflict",
    "BodyCredentialRejected",
    "BodyCredentialResult",
    "BodyInputInvalid",
    "BodyNotFound",
    "BodyPrincipal",
    "BodyResult",
    "EnrollBodyCommand",
    "ListBodiesQuery",
    "RecordBodyActivityCommand",
    "RevokeBodyCommand",
    "RotateBodyCredentialCommand",
)
