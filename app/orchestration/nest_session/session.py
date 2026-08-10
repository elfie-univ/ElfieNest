"""真实精灵实例与 Nest 活动空间的组合会话。"""

from __future__ import annotations

import logging
from threading import RLock
from typing import Dict, Literal

from app.orchestration.message_delivery import (
    GodotOwnerChannel,
    OwnerMessageBroadcaster,
    deliver_owner_message,
)
from app.orchestration.nest_session.errors import NestSessionLifecycleError
from app.orchestration.nest_session.models import ActorDescriptor, WorldEvent
from app.orchestration.nest_session.ports import (
    CorticalRuntimeFactory,
    WorldRuntimePort,
)
from app.orchestration.nest_session.residents import (
    actor_catalog,
    persist_resident,
    restore_snapshot,
)
from app.orchestration.nest_session.runtime_events import NestRuntimeEventRouter
from app.orchestration.nest_session.runtime_sync import NestRuntimeSynchronizer
from elfie import Elfie
from elfie.brain.runtime_port import CorticalRuntimePort
from elfie.communication.contracts import InboundDisposition
from nest import Nest
from nest.godot_gateway.observer import ObserverSemanticEntity
from nest.interaction.hub import TactileInput
from nest.state.models import PersistentResidentState
from nest.state.repository import (
    NestPersistenceError,
    NestPersistenceSnapshot,
    NestRepository,
)
from nest.state.store import NoHomeAvailableError, ReconciliationRequiredError

logger = logging.getLogger("app.orchestration.nest_session")

SessionLifecycleState = Literal[
    "new", "starting", "running", "stopping", "stopped", "failed"
]


class NestSession:
    """持有真实精灵实例，并把巢内事件交给对应精灵处理。"""

    def __init__(
        self,
        nest: Nest,
        world_runtime: WorldRuntimePort,
        repository: NestRepository | None = None,
    ) -> None:
        self.nest = nest
        self.world_runtime = world_runtime
        self.elfies: Dict[str, Elfie] = {}
        self._lifecycle_lock = RLock()
        self._lifecycle_state: SessionLifecycleState = "new"
        self._cortical_runtime: CorticalRuntimePort | None = None
        self._cortical_runtime_factory: CorticalRuntimeFactory | None = None
        self.owner_broadcaster: OwnerMessageBroadcaster | None = None
        self._runtime_token: tuple[str, int] | None = None
        self._repository = repository
        snapshot = (
            repository.load_snapshot()
            if repository is not None
            else NestPersistenceSnapshot(
                desired_bed_count=nest.state.config.bed_count,
                elapsed_seconds=0.0,
                catalog=None,
                residents=(),
            )
        )
        restore_snapshot(self.nest, snapshot)
        self._persisted_home_assignments = self._read_persisted_home_assignments()
        self._runtime_sync = NestRuntimeSynchronizer(
            nest=nest,
            world_runtime=world_runtime,
            actor_catalog_provider=self._actor_catalog_snapshot,
            desired_bed_count=snapshot.desired_bed_count,
            repository=repository,
        )
        self._runtime_events = NestRuntimeEventRouter(
            nest=nest,
            world_runtime=world_runtime,
            elfies=self.elfies,
            synchronizer=self._runtime_sync,
            broadcaster_provider=lambda: self.owner_broadcaster,
        )

    def register_elfie(self, elfie_id: str, elfie: Elfie) -> None:
        with self._lifecycle_lock:
            if elfie_id in self.elfies:
                raise NestSessionLifecycleError(f"Elfie 已注册: {elfie_id}")
            if self._lifecycle_state in {"starting", "stopping", "stopped", "failed"}:
                raise NestSessionLifecycleError(
                    f"NestSession 当前状态不允许注册精灵: {self._lifecycle_state}"
                )
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
                elfie.bind_identity(elfie_id)
                elfie.register_communication_channel(
                    GodotOwnerChannel(
                        owner_broadcaster=lambda: self.owner_broadcaster,
                    ),
                    connect=True,
                    replace=True,
                )
                if not elfie.cognition_configured:
                    runtime = (
                        self._cortical_runtime_factory(elfie_id)
                        if self._cortical_runtime_factory is not None
                        else self._cortical_runtime
                    )
                    if runtime is None and self._lifecycle_state == "running":
                        raise NestSessionLifecycleError(
                            "运行中的 NestSession 没有可用的认知 Runtime"
                        )
                    if runtime is not None:
                        elfie.configure_cognition(runtime)
                if self._lifecycle_state == "running":
                    elfie.start()
                    if not elfie.is_running:
                        raise NestSessionLifecycleError(
                            f"精灵 {elfie_id} 启动后未进入运行态"
                        )
            except (
                NestPersistenceError,
                NoHomeAvailableError,
                ReconciliationRequiredError,
                NestSessionLifecycleError,
                AttributeError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                if self._lifecycle_state == "running":
                    self._stop_failed_elfie(elfie)
                self._rollback_registration(
                    elfie_id,
                    was_resident=was_resident,
                    previous_home_anchor_id=previous_home_anchor_id,
                )
                raise
            self.elfies[elfie_id] = elfie
            self._runtime_sync.mark_actor_catalog_dirty()
            logger.info("精灵 '%s' 已进入 Nest", elfie_id)

    @property
    def lifecycle_state(self) -> SessionLifecycleState:
        with self._lifecycle_lock:
            return self._lifecycle_state

    def get_elfie(self, elfie_id: str) -> Elfie | None:
        with self._lifecycle_lock:
            return self.elfies.get(elfie_id)

    def elfie_items_snapshot(self) -> tuple[tuple[str, Elfie], ...]:
        with self._lifecycle_lock:
            return tuple(self.elfies.items())

    def _actor_catalog_snapshot(self) -> tuple[ActorDescriptor, ...]:
        with self._lifecycle_lock:
            return actor_catalog(self.elfies)

    def _rollback_registration(
        self,
        elfie_id: str,
        *,
        was_resident: bool,
        previous_home_anchor_id: str | None,
    ) -> None:
        if not was_resident:
            self.nest.remove_resident(elfie_id)
            if self._repository is not None:
                try:
                    self._repository.remove_resident(elfie_id)
                except NestPersistenceError as exc:
                    logger.warning(
                        "回滚精灵 %s 的 Nest 持久化状态失败: %s", elfie_id, exc
                    )
            return
        if (
            previous_home_anchor_id is None
            and self.nest.home_anchor_id(elfie_id) is not None
        ):
            self.nest.release_home(elfie_id)
            try:
                persist_resident(self.nest, self._repository, elfie_id)
            except NestPersistenceError as exc:
                logger.warning("回滚精灵 %s 的 home 状态失败: %s", elfie_id, exc)

    @staticmethod
    def _stop_failed_elfie(elfie: Elfie) -> None:
        try:
            elfie.stop()
        except RuntimeError as exc:
            logger.warning("回滚精灵 stop 失败: %s", exc)
        try:
            elfie.join()
        except RuntimeError as exc:
            logger.warning("回滚精灵 join 失败: %s", exc)

    def remove_elfie(self, elfie_id: str) -> None:
        with self._lifecycle_lock:
            existing = self.elfies.get(elfie_id)
            if existing is not None:
                transport = getattr(existing.current_body, "transport", None)
                cancel_all = getattr(transport, "cancel_all", None)
                if callable(cancel_all):
                    cancel_all(actor_id=elfie_id)
                existing.stop()
                existing.join()
            if self._repository is not None:
                self._repository.remove_resident(elfie_id)
            self.elfies.pop(elfie_id, None)
            self.nest.remove_resident(elfie_id)
            self._runtime_sync.mark_actor_catalog_dirty()

    def attach_repository(self, repository: NestRepository) -> None:
        """Attach persistence during application bootstrap before residents load."""
        with self._lifecycle_lock:
            if self._repository is not None:
                return
            if self.elfies:
                msg = (
                    "cannot attach Nest repository after Elfie instances are registered"
                )
                raise RuntimeError(msg)
            snapshot = repository.load_snapshot()
            self._repository = repository
            restore_snapshot(self.nest, snapshot)
            self._runtime_sync = NestRuntimeSynchronizer(
                nest=self.nest,
                world_runtime=self.world_runtime,
                actor_catalog_provider=self._actor_catalog_snapshot,
                desired_bed_count=snapshot.desired_bed_count,
                repository=repository,
            )
            self._runtime_events.replace_synchronizer(self._runtime_sync)
            self._persisted_home_assignments = self._read_persisted_home_assignments()

    @property
    def has_repository(self) -> bool:
        """Whether persistence was bound before the service starts loading Elfies."""
        return self._repository is not None

    def poll_runtime_connection(self) -> None:
        """Detect a new authoritative Runtime and send desired world config."""
        with self._lifecycle_lock:
            connection = self.world_runtime.runtime_connection
            token = (
                (connection.runtime_id, connection.generation)
                if connection is not None
                else None
            )
            if token != self._runtime_token:
                self._runtime_events.interrupt_native_bodies(
                    "runtime generation changed"
                )
                self._runtime_token = token
            self._runtime_sync.poll_connection()

    def consume_runtime_event(self, event: WorldEvent) -> None:
        """Apply one drained and generation-validated Runtime event."""
        with self._lifecycle_lock:
            self._runtime_events.consume(event)

    def flush_runtime_state(self) -> None:
        """Send one complete actor catalog when the matching world is ready."""
        with self._lifecycle_lock:
            self._runtime_sync.flush()

    def observer_semantic_entities(self) -> Dict[str, ObserverSemanticEntity]:
        """Expose only Nest-owned semantic facts for authenticated Observers."""
        with self._lifecycle_lock:
            self._persisted_home_assignments = self._read_persisted_home_assignments()
        catalog = self.nest.state.world_catalog
        room_id = (
            catalog.nest_id if catalog is not None else self.nest.state.config.nest_id
        )
        descriptors = {
            descriptor.actor_id: descriptor for descriptor in actor_catalog(self.elfies)
        }
        entities: Dict[str, ObserverSemanticEntity] = {}
        for elfie_id, resident in self.nest.state.residents.items():
            mirror = self.nest.state.runtime_mirrors.get(elfie_id)
            descriptor = descriptors.get(elfie_id)
            entities[elfie_id] = ObserverSemanticEntity(
                room_id=room_id,
                zone_id=mirror.current_zone_id if mirror is not None else None,
                posture=mirror.posture if mirror is not None else resident.posture,
                active=resident.active,
                active_command_id=(
                    mirror.active_command_id if mirror is not None else None
                ),
                species_id=descriptor.species if descriptor is not None else None,
                appearance=(
                    dict(descriptor.appearance) if descriptor is not None else {}
                ),
                home_anchor_id=self._observer_home_anchor_id(elfie_id),
            )
        return entities

    def _read_persisted_home_assignments(self) -> Dict[str, PersistentResidentState]:
        if self._repository is None:
            return {}
        try:
            assignments = self._repository.load_home_assignments()
        except NestPersistenceError as error:
            logger.warning("读取精灵 home assignment 失败: %s", error)
            return getattr(self, "_persisted_home_assignments", {})
        return {
            elfie_id: assignment
            for elfie_id, assignment in assignments.items()
            if assignment.home_anchor_id is not None
        }

    def _observer_home_anchor_id(self, elfie_id: str) -> str | None:
        persisted = self._persisted_home_assignments.get(elfie_id)
        if persisted is not None and persisted.home_anchor_id is not None:
            return persisted.home_anchor_id
        return self.nest.home_anchor_id(elfie_id)

    def tick_elfies(self, seconds: float) -> None:
        """推进活跃精灵自身周期；Nest 环境时钟由 Nest 单独推进。"""
        for elfie_id, elfie in self.elfie_items_snapshot():
            state = self.nest.resident_state(elfie_id)
            if state is not None and state.active and state.posture != "away":
                elfie.advance_clock(seconds)

    def configure_cognition(self, runtime: CorticalRuntimePort) -> None:
        """Inject the serialized Runtime boundary into every registered Elfie."""
        with self._lifecycle_lock:
            self._cortical_runtime = runtime
            self._cortical_runtime_factory = lambda _elfie_id: runtime
            for _elfie_id, elfie in self.elfie_items_snapshot():
                if not elfie.cognition_configured:
                    elfie.configure_cognition(runtime)

    def configure_cognition_factory(
        self,
        factory: CorticalRuntimeFactory,
    ) -> None:
        """Inject an independently configured Runtime boundary per Elfie."""
        with self._lifecycle_lock:
            self._cortical_runtime = None
            self._cortical_runtime_factory = factory
            for elfie_id, elfie in self.elfie_items_snapshot():
                if not elfie.cognition_configured:
                    elfie.configure_cognition(factory(elfie_id))

    def start_elfies(self) -> None:
        with self._lifecycle_lock:
            if self._lifecycle_state == "running":
                return
            if self._lifecycle_state in {"starting", "stopping", "stopped", "failed"}:
                raise NestSessionLifecycleError(
                    f"NestSession 当前状态不允许启动精灵: {self._lifecycle_state}"
                )
            self._lifecycle_state = "starting"
            started: list[Elfie] = []
            try:
                for _elfie_id, elfie in self.elfie_items_snapshot():
                    started.append(elfie)
                    elfie.start()
                    if not elfie.is_running:
                        raise NestSessionLifecycleError("精灵启动后未进入运行态")
            except (
                NestSessionLifecycleError,
                AttributeError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                self._lifecycle_state = "failed"
                for elfie in started:
                    self._stop_failed_elfie(elfie)
                raise
            self._lifecycle_state = "running"

    def stop_elfies(self) -> None:
        with self._lifecycle_lock:
            if self._lifecycle_state in {"new", "stopped", "failed"}:
                return
            if self._lifecycle_state == "stopping":
                return
            self._lifecycle_state = "stopping"
            for _elfie_id, elfie in self.elfie_items_snapshot():
                elfie.stop()

    def join_elfies(self) -> None:
        with self._lifecycle_lock:
            if self._lifecycle_state in {"new", "stopped"}:
                return
            for _elfie_id, elfie in self.elfie_items_snapshot():
                elfie.join()
            self._lifecycle_state = "stopped"

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
        with self._lifecycle_lock:
            elfie = self.elfies.get(elfie_id)
            if elfie is None or not elfie.is_running:
                return None
            return deliver_owner_message(
                elfie=elfie,
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

__all__ = [
    "ElfieNestCoordinator",
    "NestSession",
    "NestSessionLifecycleError",
]
