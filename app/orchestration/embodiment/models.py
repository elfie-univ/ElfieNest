"""Commands and results owned by the embodiment workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from nest.embodiment import EmbodimentState


@dataclass(frozen=True)
class ListEmbodimentSessionsQuery:
    pass


@dataclass(frozen=True)
class EmbodimentSession:
    elfie_id: str
    state: EmbodimentState
    body_id: str | None
    lease_expires_at: float | None
    lease_version: int


@dataclass(frozen=True)
class Hosted:
    session: EmbodimentSession


@dataclass(frozen=True)
class HostingFailed:
    restored_state: EmbodimentState
    reason: str


@dataclass(frozen=True)
class EmbodimentConflict:
    state: EmbodimentState
    reason: str


HostingResult = Union[Hosted, HostingFailed, EmbodimentConflict]


__all__ = (
    "EmbodimentConflict",
    "EmbodimentSession",
    "Hosted",
    "HostingFailed",
    "HostingResult",
    "ListEmbodimentSessionsQuery",
)
