"""完整精灵巢模块的唯一公开门面。"""

from __future__ import annotations

from typing import Optional, Tuple

from nest.engine.engine import InvalidTickError, NestEngine
from nest.interaction.hub import InteractionHub, SpeechInput, TactileInput
from nest.state.config import NestConfig
from nest.state.models import (
    HomeAssignment,
    ResidentState,
    RuntimeResidentMirror,
    WorldCatalog,
)
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

    def admit_resident(self, elfie_id: str) -> HomeAssignment:
        assignment = self.state.admit_resident(elfie_id)
        self._interaction.register_resident(elfie_id)
        return assignment

    def remove_resident(self, elfie_id: str) -> None:
        self.state.remove_resident(elfie_id)
        self._interaction.remove_resident(elfie_id)

    def apply_catalog(self, catalog: WorldCatalog) -> None:
        self.state.apply_catalog(catalog)

    def assign_home(self, elfie_id: str, anchor_id: str) -> HomeAssignment:
        return self.state.assign_home(elfie_id, anchor_id)

    def release_home(self, elfie_id: str) -> None:
        self.state.release_home(elfie_id)

    def home_anchor_id(self, elfie_id: str) -> str | None:
        return self.state.home_anchor_id(elfie_id)

    def apply_runtime_mirrors(
        self,
        mirrors: tuple[RuntimeResidentMirror, ...],
    ) -> None:
        self.state.apply_runtime_mirrors(mirrors)

    def update_resident_posture(
        self,
        elfie_id: str,
        posture: str,
    ) -> None:
        self.state.update_resident(elfie_id, posture)

    def broadcast_speech(self, sender_id: str, text: str) -> None:
        self._interaction.broadcast_speech(sender_id, text)

    def deliver_speech(
        self,
        *,
        sender_id: str,
        text: str,
        audience_ids: tuple[str, ...],
        event_id: str,
    ) -> None:
        self._interaction.deliver_speech(
            sender_id=sender_id,
            text=text,
            audience_ids=audience_ids,
            event_id=event_id,
        )

    def consume_sensory_input(self, elfie_id: str) -> str:
        return self._interaction.consume_sensory(elfie_id)

    def consume_speech_events(self, elfie_id: str) -> tuple[SpeechInput, ...]:
        return self._interaction.consume_speech_events(elfie_id)

    def submit_user_message(self, elfie_id: str, message: str) -> None:
        self._interaction.submit_user_message(elfie_id, message)

    def consume_user_message(self, elfie_id: str) -> str:
        return self._interaction.consume_user_message(elfie_id)

    def submit_collision(self, receiver_id: str) -> None:
        self._interaction.submit_collision(receiver_id)

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
        self._interaction.submit_tactile_contact(
            event_id=event_id,
            receiver_id=receiver_id,
            intensity=intensity,
            direction=direction,
            contact_kind=contact_kind,
            source_semantic_id=source_semantic_id,
        )

    def consume_tactile(self, elfie_id: str) -> TactileInput:
        return self._interaction.consume_tactile(elfie_id)

    def tick(self, seconds: float) -> None:
        self._engine.tick(seconds)

    def pause_clock(self) -> None:
        self.state.clock_paused = True

    def resume_clock(self) -> None:
        self.state.clock_paused = False

    def set_time_scale(self, scale: float) -> None:
        if scale <= 0:
            raise InvalidTickError(scale)
        self.state.time_scale = scale
