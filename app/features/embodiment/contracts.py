"""Feature-layer outcomes without body or database ownership."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from app.infrastructure.persistence.embodiment_sessions import EmbodimentSession
from nest.embodiment import EmbodimentState


@dataclass(frozen=True)
class Hosted:
    """A body became the Elfie's one active hosted body."""

    session: EmbodimentSession


@dataclass(frozen=True)
class HostingFailed:
    """Binding failed after a lease was acquired and released."""

    restored_state: EmbodimentState
    reason: str


@dataclass(frozen=True)
class EmbodimentConflict:
    """A concurrent or invalid transition prevented a second active body."""

    state: EmbodimentState
    reason: str


HostingResult = Union[Hosted, HostingFailed, EmbodimentConflict]
