"""巢内广播、用户消息和触觉缓冲。"""

from __future__ import annotations

from typing import Dict, List, Union

from nest.state.store import NestState

TactileValue = Union[str, float]
TactileInput = Dict[str, TactileValue]


class InteractionHub:  # noqa: MUTABLE_OK - 消息缓冲必须随事件消费而变化。
    """根据 Nest 状态传播互动，不解析精灵认知。"""

    def __init__(self, state: NestState) -> None:
        self._state = state
        self._sensory: Dict[str, List[str]] = {}
        self._user_messages: Dict[str, str] = {}
        self._tactile: Dict[str, TactileInput] = {}

    def register_resident(self, elfie_id: str) -> None:
        self._sensory.setdefault(elfie_id, [])

    def remove_resident(self, elfie_id: str) -> None:
        self._sensory.pop(elfie_id, None)
        self._user_messages.pop(elfie_id, None)
        self._tactile.pop(elfie_id, None)

    def broadcast_speech(self, sender_id: str, text: str) -> None:
        if not text:
            return
        message = f'[{sender_id} 说道]: "{text}"'
        for elfie_id, state in self._state.residents.items():
            if elfie_id != sender_id and state.active and state.posture != "away":
                self._sensory.setdefault(elfie_id, []).append(message)

    def consume_sensory(self, elfie_id: str) -> str:
        messages = self._sensory.get(elfie_id, [])
        self._sensory[elfie_id] = []
        return "；".join(messages)

    def submit_user_message(self, elfie_id: str, message: str) -> None:
        self._user_messages[elfie_id] = message

    def consume_user_message(self, elfie_id: str) -> str:
        return self._user_messages.pop(elfie_id, "")

    def submit_collision(self, receiver_id: str) -> None:
        self._tactile[receiver_id] = {
            "impact_force": 1.5,
            "impact_direction": "back",
            "gentle_stroke": 1.0,
        }

    def consume_tactile(self, elfie_id: str) -> TactileInput:
        return self._tactile.pop(
            elfie_id,
            {
                "impact_force": 0.0,
                "impact_direction": "none",
                "gentle_stroke": 0.0,
            },
        )
