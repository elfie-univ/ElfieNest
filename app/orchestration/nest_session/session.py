"""真实精灵实例与 Nest 活动空间的组合会话。"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from threading import RLock
from typing import Dict, Literal, cast
from uuid import uuid4

from app.orchestration.message_delivery import (
    GodotOwnerChannel,
    OwnerMessageBroadcaster,
    deliver_owner_message,
)
from app.orchestration.nest_session.errors import NestSessionLifecycleError
from app.orchestration.nest_session.models import (
    ActorDescriptor,
    ObserverSemanticEntity,
    RuntimeMockMotion,
    WorldEvent,
)
from app.orchestration.nest_session.ports import (
    ModelPortFactory,
    NestSessionRuntimePort,
    NestStateStoreError,
    NestStateStorePort,
    WorldSynchronizationPort,
)
from app.orchestration.nest_session.residents import (
    actor_catalog,
    persist_resident,
    restore_snapshot,
)
from app.orchestration.nest_session.runtime_events import NestRuntimeEventRouter
from app.orchestration.nest_session.runtime_sync import NestRuntimeSynchronizer
from app.orchestration.nest_session.world_perception import (
    nest_event_to_body_sensor_event,
)
from elfie.public import (
    BodySensorEvent,
    CommunicationChannel,
    Elfie,
    InboundDisposition,
    ModelPort,
)
from nest.public import (
    Nest,
    NestEventEnvelope,
    NestSnapshot,
    NoHomeAvailableError,
    PersistentResidentState,
    ReconciliationRequiredError,
)

logger = logging.getLogger("app.orchestration.nest_session")

SessionLifecycleState = Literal[
    "new", "starting", "running", "stopping", "stopped", "failed"
]


class NestSession:
    """持有真实精灵实例，并把巢内事件交给对应精灵处理。"""

    def __init__(
        self,
        nest: Nest,
        world_runtime: NestSessionRuntimePort,
        state_store: NestStateStorePort | None = None,
    ) -> None:
        self.nest = nest
        self.world_runtime = world_runtime
        self.elfies: Dict[str, Elfie] = {}
        self._lifecycle_lock = RLock()
        self._lifecycle_state: SessionLifecycleState = "new"
        self._model_port: ModelPort | None = None
        self._model_port_factory: ModelPortFactory | None = None
        self.owner_broadcaster: OwnerMessageBroadcaster | None = None
        self._runtime_token: tuple[str, int] | None = None
        self._environment_sync_token: tuple[str, int, int, str, bool, bool] | None = (
            None
        )
        self._state_store = state_store
        snapshot = (
            state_store.load_snapshot()
            if state_store is not None
            else NestSnapshot(
                desired_bed_count=nest.config.bed_count,
                elapsed_seconds=0.0,
                catalog=None,
                residents=(),
            )
        )
        restore_snapshot(self.nest, snapshot)
        self._persisted_home_assignments = self._read_persisted_home_assignments()
        self._runtime_sync = NestRuntimeSynchronizer(
            nest=nest,
            world_runtime=cast(WorldSynchronizationPort, world_runtime),
            actor_catalog_provider=self._actor_catalog_snapshot,
            desired_bed_count=snapshot.desired_bed_count,
            state_store=state_store,
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
                    self.nest.world_catalog is not None
                    and self.nest.home_anchor_id(elfie_id) is None
                ):
                    self.nest.admit_resident(elfie_id)
                persist_resident(self.nest, self._state_store, elfie_id)
                elfie.bind_identity(elfie_id)
                elfie.register_communication_channel(
                    GodotOwnerChannel(
                        owner_broadcaster=lambda: self.owner_broadcaster,
                    ),
                    connect=True,
                    replace=True,
                )
                if not elfie.cognition_configured:
                    model_port = (
                        self._model_port_factory(elfie_id)
                        if self._model_port_factory is not None
                        else self._model_port
                    )
                    if model_port is None and self._lifecycle_state == "running":
                        raise NestSessionLifecycleError(
                            "运行中的 NestSession 没有可用的认知 Runtime"
                        )
                    if model_port is not None:
                        elfie.configure_cognition(model_port)
                if self._lifecycle_state == "running":
                    elfie.start()
                    if not elfie.is_running:
                        raise NestSessionLifecycleError(
                            f"精灵 {elfie_id} 启动后未进入运行态"
                        )
            except (
                NestStateStoreError,
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

    def attach_communication_channel(
        self,
        elfie_id: str,
        channel: CommunicationChannel,
    ) -> bool:
        """Attach one injected platform channel to its explicit Elfie target."""
        with self._lifecycle_lock:
            elfie = self.elfies.get(elfie_id)
            if elfie is None:
                return False
            elfie.register_communication_channel(
                channel,
                connect=False,
                replace=True,
            )
            return True

    def detach_communication_channel(
        self,
        elfie_id: str,
        channel: CommunicationChannel,
    ) -> None:
        """Detach only the worker's own channel, preserving newer replacements."""
        with self._lifecycle_lock:
            elfie = self.elfies.get(elfie_id)
            if elfie is None:
                return
            elfie.unregister_communication_channel(
                channel.channel_id,
                expected=channel,
            )

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
            if self._state_store is not None:
                try:
                    self._state_store.save_snapshot(self.nest.export_snapshot())
                except NestStateStoreError as exc:
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
                persist_resident(self.nest, self._state_store, elfie_id)
            except NestStateStoreError as exc:
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
            self.elfies.pop(elfie_id, None)
            self.nest.remove_resident(elfie_id)
            if self._state_store is not None:
                self._state_store.save_snapshot(self.nest.export_snapshot())
            self._runtime_sync.mark_actor_catalog_dirty()

    def attach_state_store(self, state_store: NestStateStorePort) -> None:
        """Attach persistence during application bootstrap before residents load."""
        with self._lifecycle_lock:
            if self._state_store is not None:
                return
            if self.elfies:
                msg = "cannot attach Nest state store after Elfie instances are registered"
                raise RuntimeError(msg)
            snapshot = state_store.load_snapshot()
            self._state_store = state_store
            restore_snapshot(self.nest, snapshot)
            self._runtime_sync = NestRuntimeSynchronizer(
                nest=self.nest,
                world_runtime=cast(WorldSynchronizationPort, self.world_runtime),
                actor_catalog_provider=self._actor_catalog_snapshot,
                desired_bed_count=snapshot.desired_bed_count,
                state_store=state_store,
            )
            self._runtime_events.replace_synchronizer(self._runtime_sync)
            self._persisted_home_assignments = self._read_persisted_home_assignments()

    @property
    def has_state_store(self) -> bool:
        """Whether persistence was bound before the service starts loading Elfies."""
        return self._state_store is not None

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
                self.nest.invalidate_runtime_state()
                self._runtime_token = token
                self._environment_sync_token = None
            self._runtime_sync.poll_connection()

    def consume_runtime_event(self, event: WorldEvent) -> None:
        """Apply one drained and generation-validated Runtime event."""
        with self._lifecycle_lock:
            self._runtime_events.consume(event)
            self._deliver_pending_nest_events()

    def _deliver_pending_nest_events(self) -> None:
        """Deliver each typed Nest event once to its explicit Elfie targets."""
        envelopes = self.nest.drain_event_outbox()
        if not envelopes:
            return
        received_at = datetime.now(timezone.utc)
        deliveries: dict[str, list[tuple[NestEventEnvelope, BodySensorEvent]]] = {}
        for envelope in envelopes:
            for target_id in envelope.target_ids:
                elfie = self.elfies.get(target_id)
                if elfie is None:
                    logger.warning(
                        "Nest event %s targeted unknown Elfie %s",
                        envelope.event_id,
                        target_id,
                    )
                    continue
                event = nest_event_to_body_sensor_event(
                    envelope=envelope,
                    target_id=target_id,
                    elfie=elfie,
                    received_at=received_at,
                )
                if event is not None:
                    deliveries.setdefault(target_id, []).append((envelope, event))
        failed_targets_by_event: dict[str, set[str]] = {}
        for target_id, items in deliveries.items():
            elfie = self.elfies.get(target_id)
            if elfie is not None:
                try:
                    elfie.pump_body_events(tuple(event for _, event in items))
                except Exception:
                    logger.exception(
                        "Failed to deliver Nest events to Elfie %s; requeueing",
                        target_id,
                    )
                    for envelope, _ in items:
                        failed_targets_by_event.setdefault(
                            envelope.event_id, set()
                        ).add(target_id)
        if failed_targets_by_event:
            requeued = tuple(
                replace(
                    envelope,
                    target_ids=tuple(
                        target_id
                        for target_id in envelope.target_ids
                        if target_id
                        in failed_targets_by_event.get(envelope.event_id, set())
                    ),
                )
                for envelope in envelopes
                if failed_targets_by_event.get(envelope.event_id)
            )
            self.nest.requeue_event_outbox(requeued)

    def flush_runtime_state(self) -> None:
        """Send one complete actor catalog when the matching world is ready."""
        with self._lifecycle_lock:
            self._runtime_sync.flush()

    def flush_environment_state(self) -> None:
        """Synchronize Nest desired environment once per Runtime generation/state."""
        connection = self.world_runtime.runtime_connection
        revision = self._runtime_sync.configured_revision
        if connection is None or revision is None:
            return
        desired = self.nest.desired_environment
        token = (
            connection.runtime_id,
            connection.generation,
            revision,
            desired.object_id,
            desired.lights_on,
            desired.quiet_mode,
        )
        if token == self._environment_sync_token:
            return
        request = getattr(self.world_runtime, "apply_environment", None)
        if not callable(request):
            return
        command_id = f"environment-{uuid4().hex}"
        result = request(
            object_id=desired.object_id,
            command_id=command_id,
            lights_on=desired.lights_on,
            quiet_mode=desired.quiet_mode,
            world_revision=revision,
        )
        if result is not None:
            self._environment_sync_token = token

    def observer_semantic_entities(self) -> Dict[str, ObserverSemanticEntity]:
        """Expose only Nest-owned semantic facts for authenticated Observers."""
        with self._lifecycle_lock:
            self._persisted_home_assignments = self._read_persisted_home_assignments()
        catalog = self.nest.world_catalog
        room_id = catalog.nest_id if catalog is not None else self.nest.config.nest_id
        descriptors = {
            descriptor.actor_id: descriptor for descriptor in actor_catalog(self.elfies)
        }
        entities: Dict[str, ObserverSemanticEntity] = {}
        for elfie_id in self.nest.resident_ids:
            resident = self.nest.resident_state(elfie_id)
            mirror = self.nest.runtime_mirror(elfie_id)
            if resident is None:
                continue
            descriptor = descriptors.get(elfie_id)
            entities[elfie_id] = ObserverSemanticEntity(
                room_id=room_id,
                zone_id=mirror.current_zone_id if mirror is not None else None,
                posture=mirror.posture if mirror is not None else resident.posture,
                active=resident.active,
                active_command_id=(
                    mirror.active_command_id if mirror is not None else None
                ),
                mock_motion=(
                    RuntimeMockMotion(
                        waypoint=mirror.mock_motion.waypoint,
                        sequence=mirror.mock_motion.sequence,
                    )
                    if mirror is not None and mirror.mock_motion is not None
                    else None
                ),
                species_id=descriptor.species if descriptor is not None else None,
                appearance=(
                    dict(descriptor.appearance) if descriptor is not None else {}
                ),
                home_anchor_id=self._observer_home_anchor_id(elfie_id),
            )
        return entities

    def _read_persisted_home_assignments(self) -> Dict[str, PersistentResidentState]:
        if self._state_store is None:
            return {}
        try:
            residents = self._state_store.load_snapshot().residents
        except NestStateStoreError as error:
            logger.warning("读取精灵 home assignment 失败: %s", error)
            return getattr(self, "_persisted_home_assignments", {})
        return {
            resident.elfie_id: resident
            for resident in residents
            if resident.home_anchor_id is not None
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

    def persist_time_environment(self) -> None:
        """Persist the current durable Nest snapshot through the App-owned Port."""
        if self._state_store is None:
            return
        self._state_store.save_snapshot(self.nest.export_snapshot())

    def prepare_speech(self, payload: dict[str, object]) -> bool:
        """Queue content in Nest, then ask Godot only for physical reachability."""
        command_id = payload.get("command_id")
        actor_id = payload.get("actor_id")
        text = payload.get("text")
        if (
            not isinstance(command_id, str)
            or not isinstance(actor_id, str)
            or not isinstance(text, str)
        ):
            return False
        emotion_value = payload.get("emotion")
        if not self.nest.queue_speech(
            command_id=command_id,
            sender_id=actor_id,
            text=text,
            emotion=emotion_value if isinstance(emotion_value, str) else None,
        ):
            return False
        request = getattr(self.world_runtime, "request_speech_reach", None)
        if not callable(request):
            return True
        result = request(
            command_id=command_id,
            actor_id=actor_id,
            acoustic_profile=str(payload.get("speech_profile", "normal")),
            world_revision=self._runtime_world_revision(),
        )
        if result is None:
            self.nest.cancel_speech(command_id)
            return False
        return True

    def prepare_visual_observation(self, payload: dict[str, object]) -> bool:
        """Queue a short semantic observation before asking Godot for IDs."""
        observation_id = payload.get("observation_id")
        actor_id = payload.get("actor_id")
        max_results = payload.get("max_results", 32)
        if not isinstance(observation_id, str) or not isinstance(actor_id, str):
            return False
        if not isinstance(max_results, int) or isinstance(max_results, bool):
            return False
        if not self.nest.queue_visual_observation(
            observation_id=observation_id,
            observer_id=actor_id,
            max_results=max_results,
        ):
            return False
        request = getattr(self.world_runtime, "request_visual_observation", None)
        if not callable(request):
            return True
        result = request(
            observation_id=observation_id,
            actor_id=actor_id,
            max_results=max_results,
            world_revision=self._runtime_world_revision(),
        )
        if result is None:
            self.nest.cancel_visual_observation(observation_id)
            return False
        return True

    def prepare_semantic_action(self, payload: dict[str, object]) -> str | None:
        """Resolve a bounded household target before one direct Body command."""
        command_id = payload.get("command_id")
        intent_id = payload.get("intent_id")
        actor_id = payload.get("actor_id")
        body_generation = payload.get("body_generation")
        initiator = payload.get("initiator")
        target = payload.get("anchor_id")
        if (
            not isinstance(command_id, str)
            or not isinstance(intent_id, str)
            or not isinstance(actor_id, str)
            or not isinstance(body_generation, int)
            or isinstance(body_generation, bool)
            or body_generation < 1
            or initiator != "elfie"
            or not isinstance(target, str)
        ):
            return None
        return self.nest.queue_semantic_action(
            command_id=command_id,
            intent_id=intent_id,
            actor_id=actor_id,
            body_generation=body_generation,
            target=target,
        )

    def complete_semantic_action(
        self,
        payload: dict[str, object],
        result: object,
    ) -> None:
        """Record the Nest semantic outcome without duplicating Body feedback."""
        command_id = payload.get("command_id")
        actor_id = payload.get("actor_id")
        target = payload.get("anchor_id")
        if (
            not isinstance(command_id, str)
            or not isinstance(actor_id, str)
            or not isinstance(target, str)
        ):
            return
        terminal_status = getattr(result, "terminal_status", "failed")
        reason = getattr(result, "reason", "")
        events = getattr(result, "events", ())
        terminal_event = next(
            (
                event
                for event in reversed(tuple(events))
                if getattr(getattr(event, "name", None), "value", "")
                == "intent_terminal"
            ),
            None,
        )
        event_id = (
            str(getattr(terminal_event, "message_id", ""))
            if terminal_event is not None
            else f"semantic-action:{command_id}"
        )
        self.nest.complete_semantic_action(
            command_id=command_id,
            status=str(terminal_status),
            reason=str(reason) if reason else None,
            event_id=event_id,
            runtime_id=(
                str(terminal_event.runtime_id) if terminal_event is not None else None
            ),
            runtime_generation=(
                int(terminal_event.generation) if terminal_event is not None else None
            ),
            world_revision=(
                int(terminal_event.world_revision)
                if terminal_event is not None
                else None
            ),
            occurred_at=(
                getattr(terminal_event, "occurred_at", None)
                if terminal_event is not None
                else None
            ),
        )
        self._deliver_pending_nest_events()

    def _runtime_world_revision(self) -> int:
        return self._runtime_sync.configured_revision or 0

    @property
    def runtime_world_ready(self) -> bool:
        """Return whether the current Godot world passed semantic setup."""
        return bool(
            self.world_runtime.runtime_ready
            and self._runtime_sync.configured_revision is not None
            and not self.nest.reconciliation_required
        )

    def configure_cognition(self, model_port: ModelPort) -> None:
        """Inject the configured model boundary into every registered Elfie."""
        with self._lifecycle_lock:
            self._model_port = model_port
            self._model_port_factory = lambda _elfie_id: model_port
            for _elfie_id, elfie in self.elfie_items_snapshot():
                if not elfie.cognition_configured:
                    elfie.configure_cognition(model_port)

    def configure_cognition_factory(
        self,
        factory: ModelPortFactory,
    ) -> None:
        """Inject an independently configured Runtime boundary per Elfie."""
        with self._lifecycle_lock:
            self._model_port = None
            self._model_port_factory = factory
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
            # Away residents do not receive the physical Nest tick. Catch the
            # Brain clock up before stamping an owner message so the envelope
            # cannot arrive from the future relative to that Elfie's runtime.
            elapsed_seconds = self.nest.elapsed_seconds
            cognitive_elapsed = elfie.elapsed_time
            if elapsed_seconds > cognitive_elapsed:
                elfie.advance_clock(elapsed_seconds - cognitive_elapsed)
            return deliver_owner_message(
                elfie=elfie,
                elfie_id=elfie_id,
                message=message,
                elapsed_seconds=elapsed_seconds,
                owner_id=owner_id,
                conversation_id=conversation_id,
                external_message_id=external_message_id,
                account_id=account_id,
                channel_id=channel_id,
            )


ElfieNestCoordinator = NestSession

__all__ = [
    "ElfieNestCoordinator",
    "NestSession",
    "NestSessionLifecycleError",
]
