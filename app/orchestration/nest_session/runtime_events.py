"""Route validated Godot Runtime events into Nest and Elfie boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from app.orchestration.message_delivery import OwnerMessageBroadcaster
from app.orchestration.nest_session.models import (
    EnvironmentState,
    SpeechReach,
    VisualObservation,
    WorldEvent,
    WorldEventName,
)
from app.orchestration.nest_session.ports import RuntimeEventPort
from app.orchestration.nest_session.runtime_sync import NestRuntimeSynchronizer
from elfie.public import Elfie
from nest.public import EnvironmentActualState, Nest


class _BroadcasterProvider(Protocol):
    def __call__(self) -> OwnerMessageBroadcaster | None: ...


class NestRuntimeEventRouter:
    """Apply one authority-checked event without owning product lifecycle."""

    def __init__(
        self,
        *,
        nest: Nest,
        world_runtime: RuntimeEventPort,
        elfies: Mapping[str, Elfie],
        synchronizer: NestRuntimeSynchronizer,
        broadcaster_provider: _BroadcasterProvider,
    ) -> None:
        self._nest = nest
        self._world_runtime = world_runtime
        self._elfies = elfies
        self._synchronizer = synchronizer
        self._broadcaster_provider = broadcaster_provider

    def replace_synchronizer(self, synchronizer: NestRuntimeSynchronizer) -> None:
        self._synchronizer = synchronizer

    def consume(self, event: WorldEvent) -> None:
        self._synchronizer.consume(event)
        connection = self._world_runtime.runtime_connection
        if (
            connection is None
            or event.connection.runtime_id != connection.runtime_id
            or event.connection.generation != connection.generation
        ):
            return
        if (
            event.name is WorldEventName.WORLD_CONFIGURED
            and self._synchronizer.configured_revision == event.world_revision
        ):
            self._world_runtime.mark_world_configured(
                connection,
                world_revision=event.world_revision,
            )
        if (
            event.name
            in {
                WorldEventName.SPEECH_REACH,
                WorldEventName.VISUAL_OBSERVATION,
                WorldEventName.ENVIRONMENT_STATE,
                WorldEventName.WORLD_SNAPSHOT,
            }
            and event.world_revision != self._synchronizer.configured_revision
        ):
            return
        if event.name is WorldEventName.SPEECH_REACH:
            self._consume_speech(event)
        elif event.name is WorldEventName.VISUAL_OBSERVATION:
            self._consume_visual(event)
        elif event.name is WorldEventName.ENVIRONMENT_STATE:
            self._consume_environment(event)

    def interrupt_native_bodies(self, reason: str) -> None:
        for elfie in self._elfies.values():
            transport = getattr(elfie.current_body, "transport", None)
            interrupt = getattr(transport, "interrupt_pending", None)
            if callable(interrupt):
                interrupt(reason)

    def _consume_speech(self, event: WorldEvent) -> None:
        payload = event.payload
        if not isinstance(payload, SpeechReach):
            return
        speech = self._nest.complete_speech_reach(
            command_id=payload.command_id,
            audience_ids=payload.audience_actor_ids,
            event_id=event.event_id,
            runtime_id=event.connection.runtime_id,
            runtime_generation=event.connection.generation,
            world_revision=event.world_revision,
            occurred_at=event.occurred_at,
        )
        if speech is None:
            return
        text, emotion = speech
        broadcaster = self._broadcaster_provider()
        if broadcaster is not None:
            broadcaster.broadcast_to_owners(
                payload.actor_id,
                {
                    "action": "speak_event",
                    "payload": {
                        "elfie_id": payload.actor_id,
                        "text": text,
                        "emotion": emotion,
                    },
                },
            )

    def _consume_visual(self, event: WorldEvent) -> None:
        payload = event.payload
        if not isinstance(payload, VisualObservation):
            return
        self._nest.complete_visual_observation(
            observation_id=payload.observation_id,
            zone_id=payload.zone_id,
            visible_semantic_ids=payload.visible_semantic_ids,
            event_id=event.event_id,
            runtime_id=event.connection.runtime_id,
            runtime_generation=event.connection.generation,
            world_revision=event.world_revision,
            occurred_at=event.occurred_at,
        )

    def _consume_environment(self, event: WorldEvent) -> None:
        payload = event.payload
        if not isinstance(payload, EnvironmentState):
            return
        self._nest.apply_environment_actual(
            EnvironmentActualState(
                object_id=payload.object_id,
                command_id=payload.command_id,
                lights_on=payload.lights_on,
                quiet_mode=payload.quiet_mode,
                applied=payload.applied,
                reason=payload.reason,
                runtime_id=event.connection.runtime_id,
                runtime_generation=event.connection.generation,
                world_revision=event.world_revision,
            )
        )


__all__ = ["NestRuntimeEventRouter"]
