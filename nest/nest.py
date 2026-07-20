"""完整精灵巢模块的唯一公开门面。"""

from __future__ import annotations

from typing import Iterable, Optional, Tuple

from nest.engine.engine import NestEngine
from nest.interaction.hub import InteractionHub, TactileInput
from nest.state.config import NestConfig
from nest.state.models import ResidentState
from nest.state.store import NestState


class Nest:
    """组合 Nest 状态、环境时钟和互动传播。"""

    def __init__(self, config: Optional[NestConfig] = None) -> None:
        self.state = NestState(config or NestConfig())
        self._engine = NestEngine(self.state)
        self._interaction = InteractionHub(self.state)

    @property
    def resident_ids(self) -> Tuple[str, ...]:
        return tuple(self.state.residents)

    def resident_state(self, elfie_id: str) -> Optional[ResidentState]:
        return self.state.residents.get(elfie_id)

    def register_resident(self, elfie_id: str) -> None:
        self.state.register_resident(elfie_id)
        self._interaction.register_resident(elfie_id)

    def remove_resident(self, elfie_id: str) -> None:
        self.state.remove_resident(elfie_id)
        self._interaction.remove_resident(elfie_id)

    def register_scene_furniture(self, furniture_ids: Iterable[str]) -> None:
        self.state.register_furniture(furniture_ids)

    def update_resident_posture(
        self,
        elfie_id: str,
        posture: str,
        target_furniture: Optional[str] = None,
    ) -> None:
        self.state.update_resident(elfie_id, posture, target_furniture)

    def broadcast_speech(self, sender_id: str, text: str) -> None:
        self._interaction.broadcast_speech(sender_id, text)

    def consume_sensory_input(self, elfie_id: str) -> str:
        return self._interaction.consume_sensory(elfie_id)

    def submit_user_message(self, elfie_id: str, message: str) -> None:
        self._interaction.submit_user_message(elfie_id, message)

    def consume_user_message(self, elfie_id: str) -> str:
        return self._interaction.consume_user_message(elfie_id)

    def submit_collision(self, receiver_id: str) -> None:
        self._interaction.submit_collision(receiver_id)

    def consume_tactile(self, elfie_id: str) -> TactileInput:
        return self._interaction.consume_tactile(elfie_id)

    def tick(self, seconds: float) -> None:
        self._engine.tick(seconds)
