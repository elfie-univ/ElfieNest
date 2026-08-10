"""Commands, queries, results, and principals owned by external bodies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ListBodiesQuery:
    elfie_id: str


@dataclass(frozen=True)
class EnrollBodyCommand:
    elfie_id: str
    display_name: str
    body_type: str


@dataclass(frozen=True)
class RotateBodyCredentialCommand:
    elfie_id: str
    body_id: str


@dataclass(frozen=True)
class RevokeBodyCommand:
    elfie_id: str
    body_id: str


@dataclass(frozen=True)
class AuthenticateBodyCommand:
    bearer_token: str


@dataclass(frozen=True)
class RecordBodyActivityCommand:
    body_id: str
    activity: Literal["heartbeat", "sensor_event", "receipt", "command_poll"]


@dataclass(frozen=True)
class BodyResult:
    body_id: str
    display_name: str
    body_type: str
    status: str
    last_heartbeat_at: float | None


@dataclass(frozen=True)
class BodyCredentialResult:
    body_id: str
    bearer_token: str


@dataclass(frozen=True)
class BodyPrincipal:
    body_id: str
    elfie_id: str


__all__ = (
    "AuthenticateBodyCommand",
    "BodyCredentialResult",
    "BodyPrincipal",
    "BodyResult",
    "EnrollBodyCommand",
    "ListBodiesQuery",
    "RecordBodyActivityCommand",
    "RevokeBodyCommand",
    "RotateBodyCredentialCommand",
)
