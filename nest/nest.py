"""完整精灵巢模块的唯一公开门面。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

from nest.config import NestConfig
from nest.elfie_interaction.hub import NestEventBus
from nest.events import NestEventEnvelope, SemanticActionResult, SemanticVisualScene
from nest.living_rules.living import LivingRulesState
from nest.living_rules.models import (
    HomeAssignment,
    PersistentResidentState,
    ResidentPresence,
    ResidentState,
    RuntimeResidentMirror,
)
from nest.snapshot import NestSnapshot
from nest.space_facilities.catalog import SpaceFacilitiesState
from nest.space_facilities.models import (
    AnchorKind,
    EnvironmentActualState,
    FacilityDescriptor,
    WorldCatalog,
)
from nest.time_environment.clock import (
    InvalidTickError,
    TimeEnvironmentDriver,
    TimeEnvironmentState,
)
from nest.time_environment.models import (
    EnvironmentDesiredState,
    EnvironmentRule,
    LifePhase,
)


class Nest:
    """组合 Nest 状态、环境时钟和互动传播。"""

    def __init__(self, config: Optional[NestConfig] = None) -> None:
        self._config = config or NestConfig()
        self._space = SpaceFacilitiesState()
        self._living_rules = LivingRulesState.create(self._space)
        self._time_environment = TimeEnvironmentState()
        self._desired_bed_count = self._config.bed_count
        self._time_driver = TimeEnvironmentDriver(self._time_environment)
        self._interaction = NestEventBus(self._living_rules, self._space)

    @property
    def config(self) -> NestConfig:
        return self._config

    @property
    def desired_bed_count(self) -> int:
        return self._desired_bed_count

    @property
    def reconciliation_required(self) -> bool:
        return self._living_rules.reconciliation_required

    def set_reconciliation_required(self, value: bool) -> None:
        self._living_rules.reconciliation_required = value

    def export_snapshot(self) -> NestSnapshot:
        """Export only durable semantic facts; Runtime projections stay out."""
        residents = tuple(
            PersistentResidentState(
                elfie_id=elfie_id,
                presence=(
                    ResidentPresence.ACTIVE
                    if resident.active and assignment is not None
                    else (
                        ResidentPresence.AWAY
                        if not resident.active
                        else ResidentPresence.PENDING_RUNTIME
                    )
                ),
                home_zone_id=assignment.home_zone_id
                if assignment is not None
                else None,
                home_anchor_id=(
                    assignment.home_anchor_id if assignment is not None else None
                ),
            )
            for elfie_id, resident in sorted(self._living_rules.residents.items())
            for assignment in (self._living_rules.home_assignments.get(elfie_id),)
        )
        return NestSnapshot(
            desired_bed_count=self._desired_bed_count,
            elapsed_seconds=self._time_environment.elapsed_seconds,
            catalog=self._space.world_catalog,
            residents=residents,
            clock_paused=self._time_environment.clock_paused,
            time_scale=self._time_environment.time_scale,
            environment_desired=self._time_environment.environment_desired,
            environment_rules=self._time_environment.environment_rules,
        )

    def restore_snapshot(self, snapshot: NestSnapshot) -> None:
        """Restore a validated snapshot without exposing internal state to App."""
        self._desired_bed_count = snapshot.desired_bed_count
        self._time_environment.elapsed_seconds = snapshot.elapsed_seconds
        self._time_environment.clock_paused = snapshot.clock_paused
        self._time_environment.time_scale = snapshot.time_scale
        self._time_environment.set_environment_desired(snapshot.environment_desired)
        self._time_environment.environment_rules = snapshot.environment_rules
        if snapshot.catalog is not None:
            self.apply_catalog(snapshot.catalog)
        for resident in snapshot.residents:
            if self.resident_state(resident.elfie_id) is None:
                self.register_resident(resident.elfie_id)
            if (
                snapshot.catalog is not None
                and resident.home_anchor_id is not None
                and resident.home_zone_id is not None
            ):
                if self.home_anchor_id(resident.elfie_id) is None:
                    self.assign_home(resident.elfie_id, resident.home_anchor_id)

    @property
    def resident_ids(self) -> Tuple[str, ...]:
        return tuple(self._living_rules.residents)

    @property
    def elapsed_seconds(self) -> float:
        return self._time_environment.elapsed_seconds

    def resident_state(self, elfie_id: str) -> Optional[ResidentState]:
        return self._living_rules.residents.get(elfie_id)

    def runtime_mirror(self, elfie_id: str) -> RuntimeResidentMirror | None:
        return self._living_rules.runtime_mirrors.get(elfie_id)

    @property
    def runtime_mirrors(self) -> dict[str, RuntimeResidentMirror]:
        """Return a read-only-by-convention copy of current Runtime projections."""
        return dict(self._living_rules.runtime_mirrors)

    def register_resident(self, elfie_id: str) -> None:
        self._living_rules.register_resident(elfie_id)

    def admit_resident(self, elfie_id: str) -> HomeAssignment:
        assignment = self._living_rules.admit_resident(elfie_id)
        return assignment

    def remove_resident(self, elfie_id: str) -> None:
        self._living_rules.remove_resident(elfie_id)
        self._interaction.remove_resident(elfie_id)

    def apply_catalog(self, catalog: WorldCatalog) -> None:
        self._space.apply_catalog(catalog)
        self._living_rules.apply_catalog()

    @property
    def world_catalog(self) -> WorldCatalog | None:
        return self._space.world_catalog

    def facility(self, facility_id: str) -> FacilityDescriptor | None:
        catalog = self._space.world_catalog
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
        catalog = self._space.world_catalog
        if catalog is None:
            return ()
        return tuple(facility for facility in catalog.facilities if facility.active)

    def assign_home(self, elfie_id: str, anchor_id: str) -> HomeAssignment:
        return self._living_rules.assign_home(elfie_id, anchor_id)

    def release_home(self, elfie_id: str) -> None:
        self._living_rules.release_home(elfie_id)

    def home_anchor_id(self, elfie_id: str) -> str | None:
        return self._living_rules.home_anchor_id(elfie_id)

    def home_occupant(self, anchor_id: str) -> str | None:
        return self._living_rules.home_occupant(anchor_id)

    def is_home_reserved(self, anchor_id: str) -> bool:
        return self._living_rules.is_home_reserved(anchor_id)

    def can_access_home(self, elfie_id: str, anchor_id: str) -> bool:
        return self._living_rules.can_access_home(elfie_id, anchor_id)

    def apply_runtime_mirrors(
        self,
        mirrors: tuple[RuntimeResidentMirror, ...],
    ) -> None:
        self._living_rules.apply_runtime_mirrors(mirrors)

    def update_resident_posture(
        self,
        elfie_id: str,
        posture: str,
    ) -> None:
        self._living_rules.update_resident(elfie_id, posture)

    def broadcast_system(self, text: str, *, sender_id: str = "nest") -> None:
        self._interaction.broadcast_system(text, sender_id=sender_id)

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
        if not self._living_rules.is_present(actor_id):
            return None
        if target in {"home", "my_home"}:
            resolved_anchor_id = self.home_anchor_id(actor_id)
            if resolved_anchor_id is None:
                return None
            return (
                resolved_anchor_id
                if self._living_rules.authorize_semantic_target(
                    elfie_id=actor_id,
                    target=target,
                    resolved_anchor_id=resolved_anchor_id,
                )
                else None
            )
        facility_id = target.removeprefix("facility/")
        facility = self.facility(facility_id)
        if facility is None or not (
            target.startswith("facility/") or target == facility.facility_id
        ):
            return None
        catalog = self._space.world_catalog
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
                resolved_anchor_id = min(
                    candidates, key=lambda anchor: (anchor.order, anchor.anchor_id)
                ).anchor_id
                if self._living_rules.authorize_semantic_target(
                    elfie_id=actor_id,
                    target=target,
                    resolved_anchor_id=resolved_anchor_id,
                ):
                    return resolved_anchor_id
                return None
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

    def requeue_event_outbox(self, events: tuple[NestEventEnvelope, ...]) -> None:
        self._interaction.requeue_event_outbox(events)

    def invalidate_runtime_state(self) -> None:
        """Invalidate Runtime-derived projections and short-lived correlations."""
        self._living_rules.clear_runtime_mirrors()
        self._space.clear_runtime_projections()
        self._interaction.invalidate_runtime_state()

    def tick(self, seconds: float) -> None:
        self._time_driver.tick(
            seconds,
            environment_override=self._living_rules.environment_override,
        )

    def pause_clock(self) -> None:
        self._time_environment.clock_paused = True

    def resume_clock(self) -> None:
        self._time_environment.clock_paused = False

    def set_time_scale(self, scale: float) -> None:
        if scale <= 0:
            raise InvalidTickError(scale)
        self._time_environment.time_scale = scale

    @property
    def life_phase(self) -> LifePhase:
        return self._time_environment.life_phase

    @property
    def desired_environment(self) -> EnvironmentDesiredState:
        return self._time_environment.environment_desired

    @property
    def actual_environment(self) -> EnvironmentActualState | None:
        return self._space.environment_actual

    def apply_environment_actual(self, actual: EnvironmentActualState) -> None:
        self._space.apply_environment_actual(actual)

    def set_desired_environment(self, desired: EnvironmentDesiredState) -> None:
        self._time_environment.set_environment_desired(desired)

    def set_environment_override(self, desired: EnvironmentDesiredState) -> None:
        """Apply a household-wide environment decision over scheduled rules."""
        self._living_rules.set_environment_override(desired)
        self._time_environment.set_environment_desired(desired)

    def clear_environment_override(self) -> None:
        """Return environment control to the current scheduled phase rule."""
        self._living_rules.clear_environment_override()
        self._time_environment.apply_environment_rules()

    def set_environment_rules(self, rules: tuple[EnvironmentRule, ...]) -> None:
        self._time_environment.set_environment_rules(
            rules,
            environment_override=self._living_rules.environment_override,
        )
