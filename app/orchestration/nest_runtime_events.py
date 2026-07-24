"""Route validated Godot Runtime events into Nest and Elfie boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from app.orchestration.godot_owner_channel import OwnerMessageBroadcaster
from app.orchestration.runtime_gateway import RuntimeGateway
from app.orchestration.runtime_sync import NestRuntimeSynchronizer
from elfie import Elfie
from nest import Nest
from nest.godot.messages import RuntimeEventFrame


class _BroadcasterProvider(Protocol):
    def __call__(self) -> OwnerMessageBroadcaster | None: ...


class NestRuntimeEventRouter:
    """Apply one authority-checked event without owning product lifecycle."""

    def __init__(
        self,
        *,
        nest: Nest,
        gateway: RuntimeGateway,
        elfies: Mapping[str, Elfie],
        synchronizer: NestRuntimeSynchronizer,
        broadcaster_provider: _BroadcasterProvider,
    ) -> None:
        self._nest = nest
        self._gateway = gateway
        self._elfies = elfies
        self._synchronizer = synchronizer
        self._broadcaster_provider = broadcaster_provider

    def replace_synchronizer(self, synchronizer: NestRuntimeSynchronizer) -> None:
        self._synchronizer = synchronizer

    def consume(self, event: RuntimeEventFrame) -> None:
        self._synchronizer.consume(event)
        connection = self._gateway.runtime_connection
        if (
            connection is None
            or event.runtime_id != connection.runtime_id
            or event.generation != connection.generation
        ):
            return
        if (
            event.name.value == "world_ready"
            and self._synchronizer.ready_revision == event.world_revision
        ):
            self._gateway.mark_runtime_ready(
                connection,
                world_revision=event.world_revision,
            )
        if (
            event.name.value
            in {
                "intent_accepted",
                "intent_started",
                "intent_terminal",
                "movement_blocked",
                "tactile_contact",
                "speech_audience",
                "world_snapshot",
            }
            and event.world_revision != self._synchronizer.ready_revision
        ):
            return
        payload = dict(event.payload)
        for elfie in self._elfies.values():
            transport = getattr(elfie.current_body, "transport", None)
            receiver = getattr(transport, "receive_runtime_event", None)
            if callable(receiver):
                receiver(event.name.value, payload)
        if event.name.value == "speech_audience":
            self._consume_speech(event)
        elif event.name.value == "tactile_contact":
            self._consume_tactile(event)

    def interrupt_native_bodies(self, reason: str) -> None:
        for elfie in self._elfies.values():
            transport = getattr(elfie.current_body, "transport", None)
            interrupt = getattr(transport, "interrupt_pending", None)
            if callable(interrupt):
                interrupt(reason)

    def _consume_speech(self, event: RuntimeEventFrame) -> None:
        payload = event.payload
        sender_id = payload.get("actor_id")
        text = payload.get("text")
        raw_audience = payload.get("audience_actor_ids")
        if (
            not isinstance(sender_id, str)
            or not isinstance(text, str)
            or not isinstance(raw_audience, list)
            or not all(isinstance(actor_id, str) for actor_id in raw_audience)
        ):
            return
        self._nest.deliver_speech(
            sender_id=sender_id,
            text=text,
            audience_ids=tuple(
                actor_id for actor_id in raw_audience if isinstance(actor_id, str)
            ),
            event_id=event.message_id,
        )
        broadcaster = self._broadcaster_provider()
        if broadcaster is not None:
            broadcaster.broadcast_to_owners(
                sender_id,
                {
                    "action": "speak_event",
                    "payload": {"elfie_id": sender_id, "text": text},
                },
            )

    def _consume_tactile(self, event: RuntimeEventFrame) -> None:
        payload = event.payload
        actor_id = payload.get("actor_id")
        intensity = payload.get("intensity")
        direction = payload.get("direction")
        contact_kind = payload.get("contact_kind")
        source_id = payload.get("source_semantic_id")
        if (
            isinstance(actor_id, str)
            and isinstance(intensity, (int, float))
            and isinstance(direction, str)
            and isinstance(contact_kind, str)
            and isinstance(source_id, str)
        ):
            self._nest.submit_tactile_contact(
                event_id=event.message_id,
                receiver_id=actor_id,
                intensity=float(intensity),
                direction=direction,
                contact_kind=contact_kind,
                source_semantic_id=source_id,
            )


__all__ = ["NestRuntimeEventRouter"]
