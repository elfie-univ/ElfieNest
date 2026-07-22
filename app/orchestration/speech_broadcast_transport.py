"""Broadcast semantic speech text inside the Nest room."""

from __future__ import annotations

from typing import Callable, Protocol

from pydantic import JsonValue

from app.orchestration.godot_owner_channel import OwnerMessageBroadcaster
from nest import Nest


class GodotActionTransport(Protocol):
    """Transport shape used by NativeBody without importing its concrete class."""

    def connect(self, callback: Callable[[dict[str, JsonValue]], None]) -> None: ...

    def disconnect(self, callback: Callable[[dict[str, JsonValue]], None]) -> None: ...

    def send_action(self, action: str, payload: dict[str, JsonValue]) -> None: ...


class NestSpeechBroadcastTransport:
    """Forward Godot actions and mirror speech as text sensory input."""

    def __init__(
        self,
        *,
        inner: GodotActionTransport,
        nest: Nest,
        owner_broadcaster: Callable[[], OwnerMessageBroadcaster | None] | None = None,
    ) -> None:
        self.inner = inner
        self.nest = nest
        self.owner_broadcaster = owner_broadcaster or (lambda: None)

    def connect(self, callback: Callable[[dict[str, JsonValue]], None]) -> None:
        self.inner.connect(callback)

    def disconnect(self, callback: Callable[[dict[str, JsonValue]], None]) -> None:
        self.inner.disconnect(callback)

    def send_action(self, action: str, payload: dict[str, JsonValue]) -> None:
        if action == "speak_event":
            elfie_id = str(payload.get("elfie_id") or "").strip()
            text = str(payload.get("text") or "").strip()
            if elfie_id and text:
                self.nest.broadcast_speech(elfie_id, text)
                broadcaster = self.owner_broadcaster()
                if broadcaster is not None:
                    broadcaster.broadcast_to_owners(elfie_id, {
                        "action": "speak_event",
                        "payload": payload,
                    })
        self.inner.send_action(action, payload)


__all__ = ("GodotActionTransport", "NestSpeechBroadcastTransport")
