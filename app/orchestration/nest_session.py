"""真实精灵实例与 Nest 活动空间的组合会话。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict
from uuid import uuid4

from pydantic import ValidationError

from app.orchestration.godot_owner_channel import (
    GodotOwnerChannel,
    OwnerMessageBroadcaster,
)
from app.orchestration.speech_broadcast_transport import (
    NestSpeechBroadcastTransport,
)
from elfie import Elfie
from elfie.brain.runtime_port import CorticalRuntimePort
from elfie.communication import CommunicationEnvelope, MessageDirection, TextPart
from elfie.communication.contracts import InboundDisposition
from elfie.message_types import (
    ActorId,
    ActorRef,
    ElfieId,
    EventId,
    MessageMeta,
    TraceId,
)
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
        self._cortical_runtime: CorticalRuntimePort | None = None
        self.owner_broadcaster: OwnerMessageBroadcaster | None = None

    def register_elfie(self, elfie_id: str, elfie: Elfie) -> None:
        self.nest.register_resident(elfie_id)
        elfie.bind_identity(elfie_id)
        self._attach_room_speech_broadcast(elfie)
        elfie.register_communication_channel(
            GodotOwnerChannel(
                self.api_server,
                owner_broadcaster=lambda: self.owner_broadcaster,
            ),
            connect=True,
            replace=True,
        )
        if self._cortical_runtime is not None and not elfie.cognition_configured:
            elfie.configure_cognition(self._cortical_runtime)
        self.elfies[elfie_id] = elfie
        logger.info("精灵 '%s' 已进入 Nest", elfie_id)

    def _attach_room_speech_broadcast(self, elfie: Elfie) -> None:
        body = elfie.current_body
        transport = getattr(body, "transport", None)
        if transport is None or isinstance(transport, NestSpeechBroadcastTransport):
            return
        required = ("connect", "disconnect", "send_action")
        if not all(hasattr(transport, name) for name in required):
            return
        body.transport = NestSpeechBroadcastTransport(
            inner=transport,
            nest=self.nest,
            owner_broadcaster=lambda: self.owner_broadcaster,
        )

    def remove_elfie(self, elfie_id: str) -> None:
        elfie = self.elfies.pop(elfie_id, None)
        if elfie is not None:
            elfie.stop()
            elfie.join()
        self.nest.remove_resident(elfie_id)

    def tick_elfies(self, seconds: float) -> None:
        """推进活跃精灵自身周期；Nest 环境时钟由 Nest 单独推进。"""
        for elfie_id, elfie in self.elfies.items():
            state = self.nest.resident_state(elfie_id)
            if state is not None and state.active and state.posture != "away":
                elfie.advance_clock(seconds)

    def configure_cognition(self, runtime: CorticalRuntimePort) -> None:
        """Inject the serialized Runtime boundary into every registered Elfie."""
        self._cortical_runtime = runtime
        for elfie in self.elfies.values():
            if not elfie.cognition_configured:
                elfie.configure_cognition(runtime)

    def start_elfies(self) -> None:
        for elfie in self.elfies.values():
            elfie.start()

    def stop_elfies(self) -> None:
        for elfie in self.elfies.values():
            elfie.stop()

    def join_elfies(self) -> None:
        for elfie in self.elfies.values():
            elfie.join()

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

    def send_user_message(
        self,
        elfie_id: str,
        message: str,
        *,
        owner_id: str = "owner",
        conversation_id: str | None = None,
        external_message_id: str | None = None,
        account_id: str = "godot-owner",
        channel_id: str = "godot-owner",
    ) -> InboundDisposition | None:
        """Deliver owner text through the typed Communication boundary."""
        elfie = self.elfies.get(elfie_id)
        text = message.strip()
        if elfie is None or not text:
            return None
        now = datetime.fromtimestamp(self.nest.state.elapsed_seconds, timezone.utc)
        external_id = external_message_id or f"owner-message-{uuid4().hex}"
        try:
            owner = ActorRef(actor_id=ActorId(owner_id), source_kind="owner")
            envelope = CommunicationEnvelope(
                meta=MessageMeta(
                    event_id=EventId(f"owner:{external_id}"),
                    elfie_id=ElfieId(elfie_id),
                    source=owner,
                    occurred_at=now,
                    received_at=now,
                    trace_id=TraceId(f"owner-message:{external_id}"),
                ),
                account_id=account_id,
                channel_id=channel_id,
                conversation_id=conversation_id or f"owner:{owner_id}",
                sender=owner,
                recipients=(
                    ActorRef(actor_id=ActorId(elfie_id), source_kind="elfie"),
                ),
                direction=MessageDirection.INBOUND,
                external_message_id=external_id,
                dedupe_key=external_id,
                parts=(TextPart(text=text),),
            )
        except ValidationError as exc:
            logger.warning("owner 消息 envelope 校验失败: %s", exc)
            return None
        return elfie.receive_communication_envelope(envelope)

    def consume_user_message(self, elfie_id: str) -> str:
        return self.nest.consume_user_message(elfie_id)

    def consume_tactile(self, elfie_id: str) -> TactileInput:
        return self.nest.consume_tactile(elfie_id)


ElfieNestCoordinator = NestSession

__all__ = ["ElfieNestCoordinator", "NestSession"]
