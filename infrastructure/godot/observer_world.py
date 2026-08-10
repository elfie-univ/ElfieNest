"""Translate the existing Nest/Godot semantic Observer boundary to App Ports."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from app.orchestration.observer import (
    ObserverEntityRecord,
    ObserverPortError,
    ObserverWorldIntent,
)
from nest.godot_gateway.observer import (
    ObserverSemanticEntity as GatewayObserverEntity,
)
from nest.godot_gateway.observer import WorldChangingIntent as GatewayWorldIntent


class GodotObserverWorldAdapter:
    """Read semantic Nest facts and deliver only existing high-level intents."""

    def __init__(
        self,
        *,
        entities: Callable[[], Mapping[str, GatewayObserverEntity]],
        intent_sink: Callable[[GatewayWorldIntent], None],
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
        try:
            self._intent_sink(
                GatewayWorldIntent(
                    kind="request_interaction",
                    actor_id=intent.actor_id,
                    interaction=intent.interaction,
                )
            )
        except (RuntimeError, TypeError, ValueError) as error:
            raise ObserverPortError("Observer intent delivery failed") from error


__all__ = ("GodotObserverWorldAdapter",)
