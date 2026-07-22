"""Room speech broadcast stays semantic text, not synthetic audio."""

from __future__ import annotations

from typing import Callable

from pydantic import JsonValue

from app.orchestration.speech_broadcast_transport import (
    NestSpeechBroadcastTransport,
)
from nest import Nest


class RecordingTransport:
    def __init__(self) -> None:
        self.actions: list[tuple[str, dict[str, JsonValue]]] = []

    def connect(self, callback: Callable[[dict[str, JsonValue]], None]) -> None:
        del callback

    def disconnect(self, callback: Callable[[dict[str, JsonValue]], None]) -> None:
        del callback

    def send_action(self, action: str, payload: dict[str, JsonValue]) -> None:
        self.actions.append((action, payload))


class RecordingBroadcaster:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict[str, JsonValue]]] = []

    def broadcast_to_owners(
        self,
        elfie_id: str,
        message_dict: dict[str, JsonValue],
    ) -> None:
        self.messages.append((elfie_id, message_dict))


def test_speech_event_broadcasts_text_to_other_residents_without_audio() -> None:
    # Given: two active residents sharing a room and a wrapped Godot transport.
    nest = Nest()
    nest.register_resident("speaker")
    nest.register_resident("listener")
    inner = RecordingTransport()
    owner_broadcaster = RecordingBroadcaster()
    transport = NestSpeechBroadcastTransport(
        inner=inner,
        nest=nest,
        owner_broadcaster=lambda: owner_broadcaster,
    )

    # When: the speaker emits a semantic speech event with no audio URL.
    transport.send_action(
        "speak_event",
        {"elfie_id": "speaker", "text": "一起去活动区", "audio_url": ""},
    )

    # Then: Godot still receives the event, and the room carries text only.
    assert inner.actions == [
        (
            "speak_event",
            {"elfie_id": "speaker", "text": "一起去活动区", "audio_url": ""},
        )
    ]
    assert nest.consume_sensory_input("speaker") == ""
    assert "一起去活动区" in nest.consume_sensory_input("listener")
    assert owner_broadcaster.messages == [
        (
            "speaker",
            {
                "action": "speak_event",
                "payload": {
                    "elfie_id": "speaker",
                    "text": "一起去活动区",
                    "audio_url": "",
                },
            },
        )
    ]
