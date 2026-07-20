"""真实精灵实例与 Nest 活动空间的组合会话。"""

from __future__ import annotations

import logging
from typing import Dict

from elfie import Elfie
from nest import Nest
from nest.godot.api import GodotAPIServer
from nest.interaction.hub import TactileInput

logger = logging.getLogger("app.orchestration.nest_session")


class NestSession:
    """持有真实精灵实例，并把巢内事件交给对应精灵处理。"""

    def __init__(self, nest: Nest, api_server: GodotAPIServer) -> None:
        self.nest = nest
        self.api_server = api_server
        self.elfies: Dict[str, Elfie] = {}

    def register_elfie(self, elfie_id: str, elfie: Elfie) -> None:
        self.nest.register_resident(elfie_id)
        elfie.bind_identity(elfie_id)
        self.elfies[elfie_id] = elfie
        logger.info("精灵 '%s' 已进入 Nest", elfie_id)

    def remove_elfie(self, elfie_id: str) -> None:
        self.elfies.pop(elfie_id, None)
        self.nest.remove_resident(elfie_id)

    def tick_elfies(self, seconds: float) -> None:
        """推进活跃精灵自身周期；Nest 环境时钟由 Nest 单独推进。"""
        for elfie_id, elfie in self.elfies.items():
            state = self.nest.resident_state(elfie_id)
            if state is not None and state.active and state.posture != "away":
                elfie.tick(seconds)

    def trigger_elfie_interaction(
        self,
        sender_id: str,
        receiver_id: str,
        event_type: str,
    ) -> None:
        if event_type != "collision":
            return
        self.nest.submit_collision(receiver_id)
        self.api_server.send_action(
            "physical_impact_event",
            {"elfie_id": receiver_id, "impact_type": "gentle_stroke"},
        )
        logger.info("已将 %s 的碰撞刺激投递给 %s", sender_id, receiver_id)

    def send_user_message(self, elfie_id: str, message: str) -> None:
        self.nest.submit_user_message(elfie_id, message)

    def consume_user_message(self, elfie_id: str) -> str:
        return self.nest.consume_user_message(elfie_id)

    def consume_tactile(self, elfie_id: str) -> TactileInput:
        return self.nest.consume_tactile(elfie_id)


ElfieNestCoordinator = NestSession

__all__ = ["ElfieNestCoordinator", "NestSession"]
