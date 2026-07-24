"""巢内广播、用户消息和触觉缓冲。"""

from __future__ import annotations

from typing import Dict, List, TypedDict
from uuid import uuid4

from nest.state.store import NestState


class TactileInput(TypedDict):
    """One normalized, deduplicated physical contact perception."""

    intensity: float
    direction: str
    contact_kind: str
    source_semantic_id: str
    force_newtons_estimate: float


class SpeechInput(TypedDict):
    event_id: str
    sender_id: str
    text: str


class InteractionHub:  # noqa: MUTABLE_OK - 消息缓冲必须随事件消费而变化。
    """根据 Nest 状态传播互动，不解析精灵认知。"""

    def __init__(self, state: NestState) -> None:
        self._state = state
        self._sensory: Dict[str, List[SpeechInput]] = {}
        self._user_messages: Dict[str, str] = {}
        self._tactile: Dict[str, TactileInput] = {}
        self._seen_tactile_event_ids: set[str] = set()

    def register_resident(self, elfie_id: str) -> None:
        self._sensory.setdefault(elfie_id, [])

    def remove_resident(self, elfie_id: str) -> None:
        self._sensory.pop(elfie_id, None)
        self._user_messages.pop(elfie_id, None)
        self._tactile.pop(elfie_id, None)

    def broadcast_speech(self, sender_id: str, text: str) -> None:
        """Compatibility alias for a Nest-wide system announcement."""
        self.broadcast_system(text, sender_id=sender_id)

    def broadcast_system(self, text: str, *, sender_id: str = "nest") -> None:
        if not text:
            return
        event = SpeechInput(
            event_id=f"nest-system:{uuid4().hex}",
            sender_id=sender_id,
            text=text,
        )
        for elfie_id, state in self._state.residents.items():
            if elfie_id != sender_id and state.active and state.posture != "away":
                self._sensory.setdefault(elfie_id, []).append(event)

    def deliver_speech(
        self,
        *,
        sender_id: str,
        text: str,
        audience_ids: tuple[str, ...],
        event_id: str,
    ) -> None:
        if not text:
            return
        event = SpeechInput(
            event_id=event_id,
            sender_id=sender_id,
            text=text,
        )
        for elfie_id in audience_ids:
            state = self._state.residents.get(elfie_id)
            if (
                elfie_id == sender_id
                or state is None
                or not state.active
                or state.posture == "away"
            ):
                continue
            self._sensory.setdefault(elfie_id, []).append(event)

    def consume_sensory(self, elfie_id: str) -> str:
        events = self.consume_speech_events(elfie_id)
        return "；".join(
            f'[{event["sender_id"]} 说道]: "{event["text"]}"' for event in events
        )

    def consume_speech_events(self, elfie_id: str) -> tuple[SpeechInput, ...]:
        events = tuple(self._sensory.get(elfie_id, ()))
        self._sensory[elfie_id] = []
        return events

    def submit_user_message(self, elfie_id: str, message: str) -> None:
        self._user_messages[elfie_id] = message

    def consume_user_message(self, elfie_id: str) -> str:
        return self._user_messages.pop(elfie_id, "")

    def submit_collision(self, receiver_id: str) -> None:
        self.submit_tactile_contact(
            event_id=f"legacy:{receiver_id}",
            receiver_id=receiver_id,
            intensity=0.25,
            direction="back",
            contact_kind="world",
            source_semantic_id="legacy-contact",
        )

    def submit_tactile_contact(
        self,
        *,
        event_id: str,
        receiver_id: str,
        intensity: float,
        direction: str,
        contact_kind: str,
        source_semantic_id: str,
    ) -> None:
        if event_id in self._seen_tactile_event_ids:
            return
        if receiver_id not in self._state.residents:
            return
        self._seen_tactile_event_ids.add(event_id)
        normalized_intensity = min(max(float(intensity), 0.0), 1.0)
        self._tactile[receiver_id] = {
            "intensity": normalized_intensity,
            "direction": direction or "none",
            "contact_kind": contact_kind or "world",
            "source_semantic_id": source_semantic_id or "unknown",
            "force_newtons_estimate": normalized_intensity * 6.0,
        }

    def consume_tactile(self, elfie_id: str) -> TactileInput:
        return self._tactile.pop(
            elfie_id,
            {
                "intensity": 0.0,
                "direction": "none",
                "contact_kind": "none",
                "source_semantic_id": "none",
                "force_newtons_estimate": 0.0,
            },
        )
