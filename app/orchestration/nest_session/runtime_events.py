"""Route validated Godot Runtime events into Nest and Elfie boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from app.orchestration.godot_owner_channel import OwnerMessageBroadcaster
from app.orchestration.nest_session.models import (
    IntentProgress,
    IntentTerminal,
    RuntimeFailure,
    SceneManifest,
    SpeechAudience,
    TactileContact,
    WorldEvent,
    WorldEventName,
    WorldReady,
    WorldSnapshot,
)
from app.orchestration.nest_session.ports import WorldRuntimePort
from app.orchestration.nest_session.runtime_sync import NestRuntimeSynchronizer
from elfie import Elfie
from nest import Nest


class _BroadcasterProvider(Protocol):
    def __call__(self) -> OwnerMessageBroadcaster | None: ...


class NestRuntimeEventRouter:
    """Apply one authority-checked event without owning product lifecycle."""

    def __init__(
        self,
        *,
        nest: Nest,
        world_runtime: WorldRuntimePort,
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
            event.name is WorldEventName.WORLD_READY
            and self._synchronizer.ready_revision == event.world_revision
        ):
            self._world_runtime.mark_ready(
                connection,
                world_revision=event.world_revision,
            )
        if (
            event.name
            in {
                WorldEventName.INTENT_ACCEPTED,
                WorldEventName.INTENT_STARTED,
                WorldEventName.INTENT_TERMINAL,
                WorldEventName.MOVEMENT_BLOCKED,
                WorldEventName.TACTILE_CONTACT,
                WorldEventName.SPEECH_AUDIENCE,
                WorldEventName.WORLD_SNAPSHOT,
            }
            and event.world_revision != self._synchronizer.ready_revision
        ):
            return
        payload = _body_payload(event)
        for elfie in self._elfies.values():
            transport = getattr(elfie.current_body, "transport", None)
            receiver = getattr(transport, "receive_runtime_event", None)
            if callable(receiver):
                receiver(event.name.value, payload)
        if event.name is WorldEventName.SPEECH_AUDIENCE:
            self._consume_speech(event)
        elif event.name is WorldEventName.TACTILE_CONTACT:
            self._consume_tactile(event)

    def interrupt_native_bodies(self, reason: str) -> None:
        for elfie in self._elfies.values():
            transport = getattr(elfie.current_body, "transport", None)
            interrupt = getattr(transport, "interrupt_pending", None)
            if callable(interrupt):
                interrupt(reason)

    def _consume_speech(self, event: WorldEvent) -> None:
        payload = event.payload
        if not isinstance(payload, SpeechAudience):
            return
        self._nest.deliver_speech(
            sender_id=payload.actor_id,
            text=payload.text,
            audience_ids=payload.audience_actor_ids,
            event_id=event.event_id,
        )
        broadcaster = self._broadcaster_provider()
        if broadcaster is not None:
            broadcaster.broadcast_to_owners(
                payload.actor_id,
                {
                    "action": "speak_event",
                    "payload": {
                        "elfie_id": payload.actor_id,
                        "text": payload.text,
                    },
                },
            )

    def _consume_tactile(self, event: WorldEvent) -> None:
        payload = event.payload
        if isinstance(payload, TactileContact):
            self._nest.submit_tactile_contact(
                event_id=event.event_id,
                receiver_id=payload.actor_id,
                intensity=payload.intensity,
                direction=payload.direction,
                contact_kind=payload.contact_kind,
                source_semantic_id=payload.source_semantic_id,
            )


def _body_payload(event: WorldEvent) -> dict[str, object]:
    payload = event.payload
    if isinstance(payload, (IntentProgress, IntentTerminal)):
        result: dict[str, object] = {
            "command_id": payload.command_id,
            "actor_id": payload.actor_id,
        }
        if isinstance(payload, IntentTerminal):
            result["status"] = payload.status
            if payload.reason is not None:
                result["reason"] = payload.reason
            if payload.detail is not None:
                result["detail"] = payload.detail
        return result
    if isinstance(payload, TactileContact):
        return {
            "actor_id": payload.actor_id,
            "intensity": payload.intensity,
            "direction": payload.direction,
            "contact_kind": payload.contact_kind,
            "source_semantic_id": payload.source_semantic_id,
        }
    if isinstance(payload, SpeechAudience):
        return {
            "command_id": payload.command_id,
            "actor_id": payload.actor_id,
            "text": payload.text,
            "zone_id": payload.zone_id,
            "audience_actor_ids": list(payload.audience_actor_ids),
        }
    if isinstance(payload, WorldReady):
        return {
            "ready": payload.ready,
            "navigation_ready": payload.navigation_ready,
        }
    if isinstance(payload, RuntimeFailure):
        result = {"code": payload.code}
        if payload.accepted is not None:
            result["accepted"] = payload.accepted
        return result
    if isinstance(payload, WorldSnapshot):
        return {"world_revision": payload.revision}
    if isinstance(payload, SceneManifest):
        return {"nest_id": payload.catalog.nest_id}
    return {}


__all__ = ["NestRuntimeEventRouter"]
