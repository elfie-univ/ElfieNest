"""真实精灵实例与 Nest 活动空间的组合会话。"""

from __future__ import annotations

import logging
from typing import Dict

from app.orchestration.godot_owner_channel import (
    GodotOwnerChannel,
    OwnerMessageBroadcaster,
)
from app.orchestration.nest_residents import (
    actor_catalog,
    persist_resident,
    restore_snapshot,
)
from app.orchestration.nest_runtime_events import NestRuntimeEventRouter
from app.orchestration.owner_message_delivery import deliver_owner_message
from app.orchestration.runtime_gateway import RuntimeGateway
from app.orchestration.runtime_sync import NestRuntimeSynchronizer
from elfie import Elfie
from elfie.brain.runtime_port import CorticalRuntimePort
from elfie.communication.contracts import InboundDisposition
from nest import Nest
from nest.godot.messages import RuntimeEventFrame
from nest.interaction.hub import TactileInput
from nest.state.repository import (
    NestPersistenceError,
    NestPersistenceSnapshot,
    NestRepository,
)
from nest.state.store import NoHomeAvailableError, ReconciliationRequiredError

logger = logging.getLogger("app.orchestration.nest_session")


class NestSession:
    """持有真实精灵实例，并把巢内事件交给对应精灵处理。"""

    def __init__(
        self,
        nest: Nest,
        api_server: RuntimeGateway,
        repository: NestRepository | None = None,
    ) -> None:
        self.nest = nest
        self.api_server = api_server
        self.elfies: Dict[str, Elfie] = {}
        self._cortical_runtime: CorticalRuntimePort | None = None
        self.owner_broadcaster: OwnerMessageBroadcaster | None = None
        self._runtime_token: tuple[str, int] | None = None
        self._repository = repository
        snapshot = (
            repository.load_snapshot()
            if repository is not None
            else NestPersistenceSnapshot(
                desired_bed_count=4,
                elapsed_seconds=0.0,
                catalog=None,
                residents=(),
            )
        )
        restore_snapshot(self.nest, snapshot)
        self._runtime_sync = NestRuntimeSynchronizer(
            nest=nest,
            gateway=api_server,
            actor_catalog_provider=lambda: actor_catalog(self.elfies),
            desired_bed_count=snapshot.desired_bed_count,
            repository=repository,
        )
        self._runtime_events = NestRuntimeEventRouter(
            nest=nest,
            gateway=api_server,
            elfies=self.elfies,
            synchronizer=self._runtime_sync,
            broadcaster_provider=lambda: self.owner_broadcaster,
        )

    def register_elfie(self, elfie_id: str, elfie: Elfie) -> None:
        was_resident = self.nest.resident_state(elfie_id) is not None
        previous_home_anchor_id = self.nest.home_anchor_id(elfie_id)
        self.nest.register_resident(elfie_id)
        try:
            if (
                self.nest.state.world_catalog is not None
                and self.nest.home_anchor_id(elfie_id) is None
            ):
                self.nest.admit_resident(elfie_id)
            persist_resident(self.nest, self._repository, elfie_id)
        except (
            NestPersistenceError,
            NoHomeAvailableError,
            ReconciliationRequiredError,
        ):
            if not was_resident:
                self.nest.remove_resident(elfie_id)
            elif (
                previous_home_anchor_id is None
                and self.nest.home_anchor_id(elfie_id) is not None
            ):
                self.nest.release_home(elfie_id)
            raise
        elfie.bind_identity(elfie_id)
        elfie.register_communication_channel(
            GodotOwnerChannel(
                owner_broadcaster=lambda: self.owner_broadcaster,
            ),
            connect=True,
            replace=True,
        )
        if self._cortical_runtime is not None and not elfie.cognition_configured:
            elfie.configure_cognition(self._cortical_runtime)
        self.elfies[elfie_id] = elfie
        self._runtime_sync.mark_actor_catalog_dirty()
        logger.info("精灵 '%s' 已进入 Nest", elfie_id)

    def remove_elfie(self, elfie_id: str) -> None:
        existing = self.elfies.get(elfie_id)
        if existing is not None:
            transport = getattr(existing.current_body, "transport", None)
            cancel_all = getattr(transport, "cancel_all", None)
            if callable(cancel_all):
                cancel_all(actor_id=elfie_id)
        if self._repository is not None:
            self._repository.remove_resident(elfie_id)
        elfie = self.elfies.pop(elfie_id, None)
        if elfie is not None:
            elfie.stop()
            elfie.join()
        self.nest.remove_resident(elfie_id)
        self._runtime_sync.mark_actor_catalog_dirty()

    def attach_repository(self, repository: NestRepository) -> None:
        """Attach persistence during application bootstrap before residents load."""
        if self._repository is repository:
            return
        if self.elfies:
            msg = "cannot attach Nest repository after Elfie instances are registered"
            raise RuntimeError(msg)
        snapshot = repository.load_snapshot()
        self._repository = repository
        restore_snapshot(self.nest, snapshot)
        self._runtime_sync = NestRuntimeSynchronizer(
            nest=self.nest,
            gateway=self.api_server,
            actor_catalog_provider=lambda: actor_catalog(self.elfies),
            desired_bed_count=snapshot.desired_bed_count,
            repository=repository,
        )
        self._runtime_events.replace_synchronizer(self._runtime_sync)

    @property
    def has_repository(self) -> bool:
        """Whether persistence was bound before the service starts loading Elfies."""
        return self._repository is not None

    def poll_runtime_connection(self) -> None:
        """Detect a new authoritative Runtime and send desired world config."""
        connection = self.api_server.runtime_connection
        token = (
            (connection.runtime_id, connection.generation)
            if connection is not None
            else None
        )
        if token != self._runtime_token:
            self._runtime_events.interrupt_native_bodies("runtime generation changed")
            self._runtime_token = token
        self._runtime_sync.poll_connection()

    def consume_runtime_event(self, event: RuntimeEventFrame) -> None:
        """Apply one drained and generation-validated Runtime event."""
        self._runtime_events.consume(event)

    def flush_runtime_state(self) -> None:
        """Send one complete actor catalog when the matching world is ready."""
        self._runtime_sync.flush()

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
        return deliver_owner_message(
            elfie=self.elfies.get(elfie_id),
            elfie_id=elfie_id,
            message=message,
            elapsed_seconds=self.nest.state.elapsed_seconds,
            owner_id=owner_id,
            conversation_id=conversation_id,
            external_message_id=external_message_id,
            account_id=account_id,
            channel_id=channel_id,
        )

    def consume_user_message(self, elfie_id: str) -> str:
        return self.nest.consume_user_message(elfie_id)

    def consume_tactile(self, elfie_id: str) -> TactileInput:
        return self.nest.consume_tactile(elfie_id)


ElfieNestCoordinator = NestSession

__all__ = ["ElfieNestCoordinator", "NestSession"]
