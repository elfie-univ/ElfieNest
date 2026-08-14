"""完整精灵巢模块的唯一公开门面。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

from nest.engine.engine import InvalidTickError, NestEngine
from nest.events import NestEventEnvelope, SemanticActionResult, SemanticVisualScene
from nest.interaction.hub import NestEventBus, SpeechInput, VisualInput
from nest.state.config import NestConfig
from nest.state.models import (
    AnchorKind,
    EnvironmentActualState,
    EnvironmentDesiredState,
    EnvironmentRule,
    FacilityDescriptor,
    HomeAssignment,
    LifePhase,
    ResidentState,
    RuntimeResidentMirror,
    WorldCatalog,
)
from nest.state.store import NestState


class Nest:
    """组合 Nest 状态、环境时钟和互动传播。"""

    def __init__(self, config: Optional[NestConfig] = None) -> None:
        self.state = NestState(config or NestConfig())
        self._engine = NestEngine(self.state.time_environment)
        self._interaction = NestEventBus(self.state)

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

    @property
    def world_catalog(self) -> WorldCatalog | None:
        return self.state.world_catalog

    def facility(self, facility_id: str) -> FacilityDescriptor | None:
        catalog = self.state.world_catalog
        if catalog is None:
            return None
        return next(
            (
                facility
                for facility in catalog.facilities
                if facility.facility_id == facility_id and facility.active
            ),
            None,
        )

    def facilities(self) -> tuple[FacilityDescriptor, ...]:
        catalog = self.state.world_catalog
        if catalog is None:
            return ()
        return tuple(facility for facility in catalog.facilities if facility.active)

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

    def queue_speech(
        self,
        *,
        command_id: str,
        sender_id: str,
        text: str,
        emotion: str | None = None,
    ) -> bool:
        return self._interaction.queue_speech(
            command_id=command_id,
            sender_id=sender_id,
            text=text,
            emotion=emotion,
        )

    def cancel_speech(self, command_id: str) -> None:
        self._interaction.cancel_speech(command_id)

    def queue_visual_observation(
        self,
        *,
        observation_id: str,
        observer_id: str,
        max_results: int = 32,
    ) -> bool:
        return self._interaction.queue_visual_observation(
            observation_id=observation_id,
            observer_id=observer_id,
            max_results=max_results,
        )

    def cancel_visual_observation(self, observation_id: str) -> None:
        self._interaction.cancel_visual_observation(observation_id)

    def complete_visual_observation(
        self,
        *,
        observation_id: str,
        zone_id: str,
        visible_semantic_ids: tuple[str, ...],
        event_id: str,
        runtime_id: str | None = None,
        runtime_generation: int | None = None,
        world_revision: int | None = None,
        occurred_at: datetime | None = None,
    ) -> SemanticVisualScene | None:
        return self._interaction.complete_visual_observation(
            observation_id=observation_id,
            zone_id=zone_id,
            visible_semantic_ids=visible_semantic_ids,
            event_id=event_id,
            runtime_id=runtime_id,
            runtime_generation=runtime_generation,
            world_revision=world_revision,
            occurred_at=occurred_at,
        )

    def resolve_semantic_action_target(
        self,
        *,
        actor_id: str,
        target: str,
    ) -> str | None:
        if self.state.residents.get(actor_id) is None:
            return None
        if target in {"home", "my_home"}:
            return self.home_anchor_id(actor_id)
        facility_id = target.removeprefix("facility/")
        facility = self.facility(facility_id)
        if facility is None or not (
            target.startswith("facility/") or target == facility.facility_id
        ):
            return None
        catalog = self.state.world_catalog
        if catalog is None:
            return None
        preferred_kinds = {
            "rest": (AnchorKind.BED,),
            "activity": (AnchorKind.ACTIVITY, AnchorKind.CHAIR),
            "transit": (AnchorKind.ACTIVITY, AnchorKind.DOOR),
            "social": (AnchorKind.CHAIR, AnchorKind.ACTIVITY),
        }[facility.kind.value]
        for kind in preferred_kinds:
            candidates = [
                anchor
                for zone in catalog.zones
                if zone.zone_id == facility.zone_id
                for anchor in zone.anchors
                if anchor.active and anchor.kind is kind
            ]
            if candidates:
                return min(
                    candidates, key=lambda anchor: (anchor.order, anchor.anchor_id)
                ).anchor_id
        return None

    def queue_semantic_action(
        self,
        *,
        command_id: str,
        actor_id: str,
        target: str,
    ) -> str | None:
        resolved_anchor_id = self.resolve_semantic_action_target(
            actor_id=actor_id,
            target=target,
        )
        if resolved_anchor_id is None:
            return None
        if not self._interaction.queue_semantic_action(
            command_id=command_id,
            actor_id=actor_id,
            target=target,
            resolved_anchor_id=resolved_anchor_id,
        ):
            return None
        return resolved_anchor_id

    def cancel_semantic_action(self, command_id: str) -> None:
        self._interaction.cancel_semantic_action(command_id)

    def complete_semantic_action(
        self,
        *,
        command_id: str,
        status: str,
        reason: str | None,
        event_id: str,
        runtime_id: str | None = None,
        runtime_generation: int | None = None,
        world_revision: int | None = None,
        occurred_at: datetime | None = None,
    ) -> SemanticActionResult | None:
        return self._interaction.complete_semantic_action(
            command_id=command_id,
            status=status,
            reason=reason,
            event_id=event_id,
            runtime_id=runtime_id,
            runtime_generation=runtime_generation,
            world_revision=world_revision,
            occurred_at=occurred_at,
        )

    def complete_speech_reach(
        self,
        *,
        command_id: str,
        audience_ids: tuple[str, ...],
        event_id: str,
        runtime_id: str | None = None,
        runtime_generation: int | None = None,
        world_revision: int | None = None,
        occurred_at: datetime | None = None,
    ) -> tuple[str, str | None] | None:
        return self._interaction.complete_speech_reach(
            command_id=command_id,
            audience_ids=audience_ids,
            event_id=event_id,
            runtime_id=runtime_id,
            runtime_generation=runtime_generation,
            world_revision=world_revision,
            occurred_at=occurred_at,
        )

    def drain_event_outbox(self) -> tuple[NestEventEnvelope, ...]:
        return self._interaction.drain_event_outbox()

    def consume_sensory_input(self, elfie_id: str) -> str:
        return self._interaction.consume_sensory(elfie_id)

    def consume_speech_events(self, elfie_id: str) -> tuple[SpeechInput, ...]:
        return self._interaction.consume_speech_events(elfie_id)

    def consume_visual_events(self, elfie_id: str) -> tuple[VisualInput, ...]:
        return self._interaction.consume_visual_events(elfie_id)

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

    @property
    def life_phase(self) -> LifePhase:
        return self.state.life_phase

    @property
    def desired_environment(self) -> EnvironmentDesiredState:
        return self.state.environment_desired

    @property
    def actual_environment(self) -> EnvironmentActualState | None:
        return self.state.environment_actual

    def apply_environment_actual(self, actual: EnvironmentActualState) -> None:
        self.state.environment_actual = actual

    def set_desired_environment(self, desired: EnvironmentDesiredState) -> None:
        self.state.set_environment_desired(desired)

    def set_environment_rules(self, rules: tuple[EnvironmentRule, ...]) -> None:
        self.state.set_environment_rules(rules)
