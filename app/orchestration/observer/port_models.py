"""Strict models crossing the Observer workflow's world Port."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import JsonValue

from app.orchestration.nest_session import RuntimeMockMotion


@dataclass(frozen=True)
class ObserverEntityRecord:
    entity_id: str
    room_id: str
    zone_id: str | None
    posture: str
    active: bool
    active_command_id: str | None
    species_id: str | None
    appearance: tuple[tuple[str, JsonValue], ...]
    home_anchor_id: str | None
    mock_motion: RuntimeMockMotion | None = None
    action_anchor_id: str | None = None

    def __post_init__(self) -> None:
        if self.action_anchor_id is not None and (
            not isinstance(self.action_anchor_id, str) or not self.action_anchor_id
        ):
            raise ValueError("action_anchor_id must be a nonempty string or None")


@dataclass(frozen=True)
class ObserverWorldIntent:
    actor_id: str
    interaction: Literal["greet", "rest"]


__all__ = ("ObserverEntityRecord", "ObserverWorldIntent", "RuntimeMockMotion")
