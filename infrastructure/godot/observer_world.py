"""Translate the existing Nest/Godot semantic Observer boundary to App Ports."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol

from pydantic import JsonValue

from app.orchestration.observer import (
    ObserverEntityRecord,
    ObserverPortError,
    ObserverWorldIntent,
)


class _SemanticEntity(Protocol):
    @property
    def room_id(self) -> str: ...

    @property
    def zone_id(self) -> str | None: ...

    @property
    def posture(self) -> str: ...

    @property
    def active(self) -> bool: ...

    @property
    def active_command_id(self) -> str | None: ...

    @property
    def species_id(self) -> str | None: ...

    @property
    def appearance(self) -> Mapping[str, JsonValue]: ...

    @property
    def home_anchor_id(self) -> str | None: ...


class GodotObserverWorldAdapter:
    """Read semantic Nest facts and deliver only existing high-level intents."""

    def __init__(
        self,
        *,
        entities: Callable[[], Mapping[str, _SemanticEntity]],
        intent_sink: Callable[[str, str], None] | None,
    ) -> None:
        self._entities = entities
        self._intent_sink = intent_sink

    def list_entities(self) -> tuple[ObserverEntityRecord, ...]:
        try:
            projected = self._entities()
            return tuple(
                ObserverEntityRecord(
                    entity_id=entity_id,
                    room_id=entity.room_id,
                    zone_id=entity.zone_id,
                    posture=entity.posture,
                    active=entity.active,
                    active_command_id=entity.active_command_id,
                    species_id=entity.species_id,
                    appearance=tuple(sorted(entity.appearance.items())),
                    home_anchor_id=entity.home_anchor_id,
                )
                for entity_id, entity in sorted(projected.items())
            )
        except (RuntimeError, TypeError, ValueError) as error:
            raise ObserverPortError("Observer semantic projection failed") from error

    def submit_intent(self, intent: ObserverWorldIntent) -> None:
        if self._intent_sink is None:
            raise ObserverPortError("Observer intent delivery is unavailable")
        try:
            self._intent_sink(intent.actor_id, intent.interaction)
        except (RuntimeError, TypeError, ValueError) as error:
            raise ObserverPortError("Observer intent delivery failed") from error


__all__ = ("GodotObserverWorldAdapter",)
