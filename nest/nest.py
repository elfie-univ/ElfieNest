"""完整精灵巢模块的唯一公开门面。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

from nest.config import NestConfig
from nest.elfie_interaction.hub import NestEventBus
from nest.events import NestEventEnvelope, SemanticActionResult, SemanticVisualScene
from nest.living_rules.errors import BedConflictError
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
from nest.space_facilities.errors import UnknownAnchorError
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
        """Restore the complete durable resident and world semantic state."""
        self._desired_bed_count = snapshot.desired_bed_count
        self._time_environment.elapsed_seconds = snapshot.elapsed_seconds
        self._time_environment.clock_paused = snapshot.clock_paused
        self._time_environment.time_scale = snapshot.time_scale
        self._time_environment.set_environment_desired(snapshot.environment_desired)
        self._time_environment.environment_rules = snapshot.environment_rules
        if snapshot.catalog is not None:
            self.apply_catalog(snapshot.catalog)
        else:
            # Replacement restore must also remove a catalog that belonged to
            # the previous aggregate instance.
            self._space.world_catalog = None
        self._space.clear_runtime_projections()

        # A snapshot is a replacement of durable Nest state, not a merge.  Do
        # not leave residents, homes, Runtime mirrors or pending events from a
        # previous aggregate instance behind.
        self._interaction.invalidate_runtime_state()
        self._living_rules.residents.clear()
        self._living_rules.home_assignments.clear()
        self._living_rules.runtime_mirrors.clear()
        self._living_rules.environment_override = None
        self._living_rules.reconciliation_required = False
        for resident in snapshot.residents:
            if resident.elfie_id in self._living_rules.residents:
                raise ValueError(f"duplicate resident in snapshot: {resident.elfie_id}")
            self._living_rules.residents[resident.elfie_id] = ResidentState(
                elfie_id=resident.elfie_id,
                posture=(
                    "away" if resident.presence is ResidentPresence.AWAY else "standing"
                ),
                active=resident.presence is not ResidentPresence.AWAY,
            )
            if (
                snapshot.catalog is not None
                and resident.home_anchor_id is not None
                and resident.home_zone_id is not None
            ):
                try:
                    self._living_rules.assign_home(
                        resident.elfie_id,
                        resident.home_anchor_id,
                    )
                except (BedConflictError, UnknownAnchorError):
                    # Preserve the resident and let orchestration surface the
                    # explicit reconciliation state instead of silently
                    # assigning a different bed.
                    self._living_rules.reconciliation_required = True

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
        self._interaction.emit_fact_notice(
            fact_type="home_assignment_changed",
            fact_id=elfie_id,
            summary=f"{elfie_id} assigned home {assignment.home_anchor_id}",
            target_ids=(elfie_id,),
            zone_id=assignment.home_zone_id,
            active=True,
        )
        return assignment

    def remove_resident(self, elfie_id: str) -> None:
        self._living_rules.remove_resident(elfie_id)
        self._interaction.remove_resident(elfie_id)

    def apply_catalog(self, catalog: WorldCatalog) -> None:
        previous = self._space.world_catalog
        self._space.apply_catalog(catalog)
        self._living_rules.apply_catalog()
        # Loading the first authoritative catalog establishes the semantic
        # baseline; it is not a state transition that residents need to
        # consume.  Emit facility notices only for changes after that baseline
        # so startup does not masquerade as a burst of world broadcasts.
        if previous is None:
            return
        previous_facilities = {
            facility.facility_id: facility
            for facility in (() if previous is None else previous.facilities)
        }
        current_facilities = {
            facility.facility_id: facility for facility in catalog.facilities
        }
        for facility_id in sorted(set(previous_facilities) | set(current_facilities)):
            before = previous_facilities.get(facility_id)
            after = current_facilities.get(facility_id)
            if before == after:
                continue
            changed = after or before
            if changed is None:
                continue
            self._interaction.emit_fact_notice(
                fact_type="facility_state_changed",
                fact_id=facility_id,
                summary=(
                    f"facility {facility_id} is "
                    f"{'active' if after is not None and after.active else 'inactive'}"
                ),
                cause_id=f"catalog:{catalog.revision}:{facility_id}",
                zone_id=changed.zone_id,
                active=bool(after is not None and after.active),
            )

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
        assignment = self._living_rules.assign_home(elfie_id, anchor_id)
        self._interaction.emit_fact_notice(
            fact_type="home_assignment_changed",
            fact_id=elfie_id,
            summary=f"{elfie_id} assigned home {anchor_id}",
            target_ids=(elfie_id,),
            zone_id=assignment.home_zone_id,
            active=True,
        )
        return assignment

    def release_home(self, elfie_id: str) -> None:
        previous = self._living_rules.home_assignments.get(elfie_id)
        self._living_rules.release_home(elfie_id)
        if previous is not None:
            self._interaction.emit_fact_notice(
                fact_type="home_assignment_changed",
                fact_id=elfie_id,
                summary=f"{elfie_id} released home {previous.home_anchor_id}",
                target_ids=(elfie_id,),
                zone_id=previous.home_zone_id,
                active=False,
            )

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
        intent_id: str,
        actor_id: str,
        body_generation: int,
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
            intent_id=intent_id,
            actor_id=actor_id,
            body_generation=body_generation,
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
        previous_phase = self.life_phase
        previous_environment = self.desired_environment
        self._time_driver.tick(
            seconds,
            environment_override=self._living_rules.environment_override,
        )
        current_phase = self.life_phase
        current_environment = self.desired_environment
        if current_phase is not previous_phase:
            self._interaction.emit_fact_notice(
                fact_type="environment_phase_changed",
                fact_id=f"phase:{current_phase.value}",
                summary=f"Nest phase changed to {current_phase.value}",
                phase=current_phase.value,
            )
        if current_environment != previous_environment:
            self._interaction.emit_fact_notice(
                fact_type="environment_desired_changed",
                fact_id=current_environment.object_id,
                summary=f"Environment desired state changed for {current_environment.object_id}",
                lights_on=current_environment.lights_on,
                quiet_mode=current_environment.quiet_mode,
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
        previous = self.desired_environment
        self._time_environment.set_environment_desired(desired)
        if desired != previous:
            self._interaction.emit_fact_notice(
                fact_type="environment_desired_changed",
                fact_id=desired.object_id,
                summary=f"Environment desired state changed for {desired.object_id}",
                lights_on=desired.lights_on,
                quiet_mode=desired.quiet_mode,
            )

    def set_environment_override(self, desired: EnvironmentDesiredState) -> None:
        """Apply a household-wide environment decision over scheduled rules."""
        self._living_rules.set_environment_override(desired)
        self.set_desired_environment(desired)

    def clear_environment_override(self) -> None:
        """Return environment control to the current scheduled phase rule."""
        self._living_rules.clear_environment_override()
        previous = self.desired_environment
        self._time_environment.apply_environment_rules()
        desired = self.desired_environment
        if desired != previous:
            self._interaction.emit_fact_notice(
                fact_type="environment_desired_changed",
                fact_id=desired.object_id,
                summary=f"Environment desired state changed for {desired.object_id}",
                lights_on=desired.lights_on,
                quiet_mode=desired.quiet_mode,
            )

    def set_environment_rules(self, rules: tuple[EnvironmentRule, ...]) -> None:
        previous_rules = self._time_environment.environment_rules
        previous_environment = self.desired_environment
        self._time_environment.set_environment_rules(
            rules,
            environment_override=self._living_rules.environment_override,
        )
        for rule in rules:
            if rule not in previous_rules:
                self._interaction.emit_fact_notice(
                    fact_type="environment_rule_changed",
                    fact_id=rule.rule_id,
                    summary=f"Environment rule {rule.rule_id} configured",
                    phase=rule.phase.value,
                    lights_on=rule.lights_on,
                    quiet_mode=rule.quiet_mode,
                )
        if self.desired_environment != previous_environment:
            desired = self.desired_environment
            self._interaction.emit_fact_notice(
                fact_type="environment_desired_changed",
                fact_id=desired.object_id,
                summary=f"Environment desired state changed for {desired.object_id}",
                lights_on=desired.lights_on,
                quiet_mode=desired.quiet_mode,
            )
