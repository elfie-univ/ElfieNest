"""Strict models crossing the Observer workflow's world Port."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import JsonValue

from app.orchestration.nest_session.models import RuntimeMockMotion


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


@dataclass(frozen=True)
class ObserverWorldIntent:
    actor_id: str
    interaction: Literal["greet", "rest"]


__all__ = ("ObserverEntityRecord", "ObserverWorldIntent")
