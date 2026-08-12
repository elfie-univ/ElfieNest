"""Technical boundaries consumed by the external-bodies Feature."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class BodiesPortError(RuntimeError):
    """A bodies persistence or credential operation failed."""


class BodiesPortNotFound(BodiesPortError):
    """The requested Elfie/body association does not exist."""


class BodiesPortConflict(BodiesPortError):
    """The requested body mutation conflicts with an active lease."""


class BodiesPortCredentialRejected(BodiesPortError):
    """The supplied independent body credential is invalid or revoked."""


@dataclass(frozen=True)
class BodyRecord:
    body_id: str
    owner_elfie_id: str
    display_name: str
    body_type: str
    status: str
    last_heartbeat_at: float | None


@dataclass(frozen=True)
class BodyCredentialRecord:
    body_id: str
    secret: str


class BodiesPort(Protocol):
    def list_for_elfie(
        self, *, owner_user_id: int, elfie_id: str
    ) -> tuple[BodyRecord, ...]: ...

    def enroll(
        self,
        *,
        owner_user_id: int,
        elfie_id: str,
        display_name: str,
        body_type: str,
    ) -> BodyCredentialRecord: ...

    def rotate(
        self, *, owner_user_id: int, elfie_id: str, body_id: str
    ) -> BodyCredentialRecord: ...

    def revoke(self, *, owner_user_id: int, elfie_id: str, body_id: str) -> None: ...

    def authenticate(self, bearer_token: str) -> BodyRecord: ...

    def record_activity(self, body_id: str, activity: str) -> None: ...


__all__ = (
    "BodiesPort",
    "BodiesPortConflict",
    "BodiesPortCredentialRejected",
    "BodiesPortError",
    "BodiesPortNotFound",
    "BodyCredentialRecord",
    "BodyRecord",
)
