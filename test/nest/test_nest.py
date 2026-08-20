import pytest

from nest import Nest
from nest.living_rules.errors import (
    BedCapacityError,
    BedConflictError,
    NoHomeAvailableError,
    UnknownResidentError,
)
from nest.living_rules.models import (
    PersistentResidentState,
    ResidentPresence,
    ResidentState,
)
from nest.snapshot import NestSnapshot
from nest.time_environment.clock import InvalidTickError


def _catalog_with_beds(count: int):
    from nest.space_facilities.models import (
        AnchorKind,
        InteractionAnchor,
        WorldCatalog,
        ZoneDescriptor,
    )

    return WorldCatalog(
        nest_id="local-nest",
        revision=1,
        zones=(
            ZoneDescriptor(
                zone_id="dorm-01",
                label="Dormitory",
                order=1,
                anchors=tuple(
                    InteractionAnchor(
                        anchor_id=f"dorm-01/bed-{index:02d}",
                        kind=AnchorKind.BED,
                        label=f"Bed {index}",
                        order=index,
                    )
                    for index in range(1, count + 1)
                ),
            ),
        ),
    )


def test_nest_registers_only_resident_identity_and_state() -> None:
    # Given
    nest = Nest()

    # When
    nest.register_resident("elfie-1")

    # Then
    resident = nest.resident_state("elfie-1")
    assert resident is not None
    assert resident.posture == "standing"
    assert nest.resident_ids == ("elfie-1",)


def test_restore_snapshot_replaces_residents_and_restores_presence() -> None:
    nest = Nest()
    catalog = _catalog_with_beds(2)
    nest.apply_catalog(catalog)
    nest.register_resident("stale")

    nest.restore_snapshot(
        NestSnapshot(
            desired_bed_count=4,
            elapsed_seconds=0.0,
            catalog=catalog,
            residents=(
                PersistentResidentState(
                    elfie_id="away-1",
                    presence=ResidentPresence.AWAY,
                    home_zone_id="dorm-01",
                    home_anchor_id="dorm-01/bed-01",
                ),
                PersistentResidentState(
                    elfie_id="pending-1",
                    presence=ResidentPresence.PENDING_RUNTIME,
                    home_zone_id="dorm-01",
                    home_anchor_id="dorm-01/bed-02",
                ),
            ),
        )
    )

    assert nest.resident_ids == ("away-1", "pending-1")
    assert nest.resident_state("away-1") == ResidentState(
        elfie_id="away-1", posture="away", active=False
    )
    assert nest.resident_state("pending-1") is not None
    assert nest.resident_state("pending-1").active is True
    assert nest.resident_state("pending-1").posture == "standing"
    assert nest.home_anchor_id("away-1") == "dorm-01/bed-01"
    assert nest.home_anchor_id("pending-1") == "dorm-01/bed-02"
    assert nest.resident_state("stale") is None


def test_restore_snapshot_clears_previous_catalog_runtime_projection_and_override() -> (
    None
):
    from nest.space_facilities.models import EnvironmentActualState
    from nest.time_environment.models import EnvironmentDesiredState

    nest = Nest()
    nest.apply_catalog(_catalog_with_beds(1))
    nest.apply_environment_actual(
        EnvironmentActualState(
            object_id="nest/environment",
            command_id="old-environment",
            lights_on=False,
            quiet_mode=True,
            applied=True,
            runtime_id="runtime-old",
            runtime_generation=1,
            world_revision=1,
        )
    )
    nest.set_environment_override(
        EnvironmentDesiredState(lights_on=False, quiet_mode=True)
    )

    nest.restore_snapshot(
        NestSnapshot(
            desired_bed_count=4,
            elapsed_seconds=0.0,
            catalog=None,
            residents=(),
            environment_desired=EnvironmentDesiredState(
                lights_on=True,
                quiet_mode=False,
            ),
        )
    )

    assert nest.world_catalog is None
    assert nest.actual_environment is None
    nest.tick(1.0)
    assert nest.desired_environment == EnvironmentDesiredState(
        lights_on=True,
        quiet_mode=False,
    )


def test_broadcast_emits_one_targeted_typed_event() -> None:
    # Given
    nest = Nest()
    nest.register_resident("elfie-1")
    nest.register_resident("elfie-2")

    # When
    nest.broadcast_system("一起去活动区", sender_id="elfie-1")

    # Then
    events = nest.drain_event_outbox()
    assert len(events) == 1
    assert events[0].target_ids == ("elfie-2",)
    assert events[0].payload.text == "一起去活动区"
    assert not hasattr(nest, "broadcast_speech")
    assert not hasattr(nest, "consume_sensory_input")


def test_non_interaction_owners_emit_through_the_common_typed_outbox() -> None:
    from nest.events import NestFactNotice
    from nest.space_facilities.models import FacilityDescriptor, FacilityKind
    from nest.time_environment.models import EnvironmentRule, LifePhase

    nest = Nest()
    nest.register_resident("elfie-1")
    nest.apply_catalog(_catalog_with_beds(1))
    assert nest.drain_event_outbox() == ()
    catalog = _catalog_with_beds(1).model_copy(
        update={
            "facilities": (
                FacilityDescriptor(
                    facility_id="dorm-01/rest",
                    zone_id="dorm-01",
                    kind=FacilityKind.REST,
                    label="Rest",
                    capabilities=("sleep",),
                ),
            )
        }
    )

    nest.apply_catalog(catalog)
    facility_event = nest.drain_event_outbox()[0]
    assert facility_event.owner == "nest.space_facilities"
    assert isinstance(facility_event.payload, NestFactNotice)
    assert facility_event.payload.fact_id == "dorm-01/rest"
    assert facility_event.target_ids == ("elfie-1",)

    nest.set_environment_rules(
        (
            EnvironmentRule(
                rule_id="quiet-night",
                phase=LifePhase.NIGHT,
                lights_on=False,
                quiet_mode=True,
            ),
        )
    )
    rule_events = nest.drain_event_outbox()
    assert {event.payload.fact_type for event in rule_events} == {
        "environment_rule_changed",
        "environment_desired_changed",
    }

    nest.tick(8 * 60 * 60)
    phase_events = nest.drain_event_outbox()
    assert any(
        isinstance(event.payload, NestFactNotice)
        and event.payload.fact_type == "environment_phase_changed"
        for event in phase_events
    )


def test_nest_keeps_semantic_posture_without_copying_godot_furniture() -> None:
    nest = Nest()
    nest.register_resident("elfie-1")

    nest.update_resident_posture("elfie-1", "sitting")

    resident = nest.resident_state("elfie-1")
    assert resident is not None and resident.posture == "sitting"
    assert not hasattr(nest, "furniture")


def test_nest_tick_advances_environment_without_an_elfie_instance() -> None:
    # Given
    nest = Nest()

    # When
    nest.tick(1.5)

    # Then
    assert nest.elapsed_seconds == 1.5


def test_nest_rejects_negative_tick() -> None:
    # Given
    nest = Nest()

    # When / Then
    with pytest.raises(InvalidTickError):
        nest.tick(-0.1)


def test_nest_changes_desired_capacity_without_a_second_config_fact() -> None:
    nest = Nest()

    assert nest.set_desired_bed_count(32) is True
    assert nest.set_desired_bed_count(32) is False
    assert nest.desired_bed_count == 32


def test_nest_rejects_capacity_that_would_remove_an_assigned_home() -> None:
    nest = Nest()
    nest.apply_catalog(_catalog_with_beds(8))
    nest.register_resident("fox-1")
    nest.assign_home("fox-1", "dorm-01/bed-08")

    with pytest.raises(BedCapacityError, match="bed-08"):
        nest.set_desired_bed_count(4)

    assert nest.desired_bed_count == 4
    assert nest.home_anchor_id("fox-1") == "dorm-01/bed-08"


def test_nest_admits_residents_with_stable_home_assignment() -> None:
    # Given
    nest = Nest()
    nest.apply_catalog(_catalog_with_beds(3))

    # When
    first = nest.admit_resident("fox-1")
    second = nest.admit_resident("dog-1")

    # Then
    assert first.home_anchor_id == "dorm-01/bed-01"
    assert second.home_anchor_id == "dorm-01/bed-02"
    assert nest.home_anchor_id("fox-1") == "dorm-01/bed-01"


def test_nest_rejects_home_conflicts_and_full_catalog() -> None:
    # Given
    nest = Nest()
    nest.apply_catalog(_catalog_with_beds(1))
    nest.admit_resident("fox-1")

    # When / Then
    with pytest.raises(NoHomeAvailableError):
        nest.admit_resident("dog-1")
    nest.register_resident("dog-1")
    with pytest.raises(BedConflictError):
        nest.assign_home("dog-1", "dorm-01/bed-01")


def test_home_assignment_is_the_single_reservation_and_access_rule() -> None:
    nest = Nest()
    nest.apply_catalog(_catalog_with_beds(1))
    nest.admit_resident("fox-1")
    nest.register_resident("dog-1")

    assert nest.is_home_reserved("dorm-01/bed-01") is True
    assert nest.home_occupant("dorm-01/bed-01") == "fox-1"
    assert nest.can_access_home("fox-1", "dorm-01/bed-01") is True
    assert nest.can_access_home("dog-1", "dorm-01/bed-01") is False

    nest.update_resident_posture("fox-1", "away")
    assert nest.can_access_home("fox-1", "dorm-01/bed-01") is False


def test_nest_catalog_shrink_marks_reconciliation_required() -> None:
    # Given
    nest = Nest()
    nest.apply_catalog(_catalog_with_beds(2))
    nest.admit_resident("fox-1")
    nest.drain_event_outbox()

    # When
    nest.apply_catalog(_catalog_with_beds(0))

    # Then
    assert nest.reconciliation_required is True
    assert nest.home_anchor_id("fox-1") == "dorm-01/bed-01"


def test_nest_exposes_active_facilities_without_geometry() -> None:
    from nest.space_facilities.models import FacilityDescriptor, FacilityKind

    nest = Nest()
    catalog = _catalog_with_beds(1).model_copy(
        update={
            "facilities": (
                FacilityDescriptor(
                    facility_id="dorm-01/rest",
                    zone_id="dorm-01",
                    kind=FacilityKind.REST,
                    label="Rest area",
                    capabilities=("sleep",),
                ),
            )
        }
    )
    nest.apply_catalog(catalog)

    assert nest.facility("dorm-01/rest") is not None
    assert nest.facilities()[0].capabilities == ("sleep",)
    assert not hasattr(nest.facility("dorm-01/rest"), "position")


def test_semantic_visual_observation_filters_candidates_and_emits_targeted_event() -> (
    None
):
    from nest.living_rules.models import RuntimeResidentMirror
    from nest.space_facilities.models import (
        FacilityDescriptor,
        FacilityKind,
    )

    nest = Nest()
    catalog = _catalog_with_beds(2).model_copy(
        update={
            "facilities": (
                FacilityDescriptor(
                    facility_id="dorm-01/rest",
                    zone_id="dorm-01",
                    kind=FacilityKind.REST,
                    label="Rest area",
                    capabilities=("sleep",),
                ),
            )
        }
    )
    nest.apply_catalog(catalog)
    nest.register_resident("fox-1")
    nest.register_resident("dog-1")
    nest.apply_runtime_mirrors(
        (
            RuntimeResidentMirror(
                elfie_id="dog-1",
                current_zone_id="dorm-01",
                runtime_id="runtime-a",
                runtime_generation=1,
                world_revision=1,
            ),
        )
    )

    assert nest.queue_visual_observation(
        observation_id="vision-1",
        observer_id="fox-1",
        max_results=2,
    )
    scene = nest.complete_visual_observation(
        observation_id="vision-1",
        zone_id="dorm-01",
        visible_semantic_ids=(
            "actor/dog-1",
            "actor/unknown",
            "anchor/dorm-01/bed-01",
            "facility/dorm-01/rest",
        ),
        event_id="vision-event-1",
    )

    assert scene is not None
    assert [entity.semantic_id for entity in scene.entities] == [
        "actor/dog-1",
        "anchor/dorm-01/bed-01",
    ]
    assert nest.drain_event_outbox()[0].target_ids == ("fox-1",)
    assert not hasattr(nest, "consume_visual_events")
    assert (
        nest.complete_visual_observation(
            observation_id="vision-1",
            zone_id="dorm-01",
            visible_semantic_ids=(),
            event_id="vision-event-1",
        )
        is None
    )


def test_semantic_home_action_resolves_once_and_records_physical_terminal() -> None:
    nest = Nest()
    nest.apply_catalog(_catalog_with_beds(2))
    nest.admit_resident("fox-1")
    nest.drain_event_outbox()

    assert (
        nest.queue_semantic_action(
            command_id="home-1",
            intent_id="intent-home-1",
            actor_id="fox-1",
            body_generation=1,
            target="home",
        )
        == "dorm-01/bed-01"
    )
    assert (
        nest.resolve_semantic_action_target(
            actor_id="fox-1",
            target="home",
        )
        == "dorm-01/bed-01"
    )
    result = nest.complete_semantic_action(
        command_id="home-1",
        status="completed",
        reason=None,
        event_id="terminal-home-1",
    )

    assert result is not None
    assert result.resolved_anchor_id == "dorm-01/bed-01"
    assert result.status == "completed"
    envelope = nest.drain_event_outbox()
    assert envelope[0].owner == "nest.action"
    assert envelope[0].target_ids == ("fox-1",)


def test_semantic_facility_action_resolves_to_one_zone_anchor() -> None:
    from nest.space_facilities.models import (
        FacilityDescriptor,
        FacilityKind,
        InteractionAnchor,
    )

    nest = Nest()
    catalog = _catalog_with_beds(1).model_copy(
        update={
            "zones": (
                _catalog_with_beds(1)
                .zones[0]
                .model_copy(
                    update={
                        "anchors": (
                            *_catalog_with_beds(1).zones[0].anchors,
                            InteractionAnchor(
                                anchor_id="dorm-01/activity",
                                kind="activity",
                                label="Activity",
                                order=99,
                            ),
                        )
                    }
                ),
            ),
            "facilities": (
                FacilityDescriptor(
                    facility_id="dorm-01/activity",
                    zone_id="dorm-01",
                    kind=FacilityKind.ACTIVITY,
                    label="Activity",
                    capabilities=("social",),
                ),
            ),
        }
    )
    nest.apply_catalog(catalog)
    nest.register_resident("fox-1")

    assert (
        nest.resolve_semantic_action_target(
            actor_id="fox-1",
            target="facility/dorm-01/activity",
        )
        == "dorm-01/activity"
    )
    assert (
        nest.resolve_semantic_action_target(
            actor_id="fox-1",
            target="unapproved/dorm-01/activity",
        )
        is None
    )

    nest.update_resident_posture("fox-1", "away")
    assert (
        nest.resolve_semantic_action_target(
            actor_id="fox-1",
            target="facility/dorm-01/activity",
        )
        is None
    )


def test_nest_rejects_unknown_resident_update() -> None:
    # Given
    nest = Nest()

    # When / Then
    with pytest.raises(UnknownResidentError):
        nest.update_resident_posture("missing", "standing")


def test_nest_clock_pause_and_time_scale() -> None:
    # Given
    nest = Nest()

    # When
    nest.set_time_scale(2.0)
    nest.tick(1.5)
    nest.pause_clock()
    nest.tick(10)
    nest.resume_clock()
    nest.tick(1)

    # Then
    assert nest.elapsed_seconds == 5.0


def test_nest_exposes_deterministic_life_phase_and_environment_rules() -> None:
    from nest.public import EnvironmentDesiredState, EnvironmentRule, LifePhase

    nest = Nest()
    nest.set_environment_rules(
        (
            EnvironmentRule(
                rule_id="night-lights-off",
                phase=LifePhase.NIGHT,
                lights_on=False,
                quiet_mode=True,
            ),
        )
    )

    assert nest.life_phase is LifePhase.NIGHT
    assert nest.desired_environment == EnvironmentDesiredState(
        lights_on=False,
        quiet_mode=True,
    )

    nest.tick(7 * 3600)

    assert nest.life_phase is LifePhase.DAWN
    assert nest.desired_environment.lights_on is False


def test_environment_override_wins_until_household_clears_it() -> None:
    from nest.public import EnvironmentDesiredState, EnvironmentRule, LifePhase

    nest = Nest()
    nest.set_environment_rules(
        (
            EnvironmentRule(
                rule_id="day-lights-on",
                phase=LifePhase.DAY,
                lights_on=True,
                quiet_mode=False,
            ),
        )
    )
    nest.set_environment_override(
        EnvironmentDesiredState(lights_on=False, quiet_mode=True)
    )

    nest.tick(12 * 3600)
    assert nest.life_phase is LifePhase.DAY
    assert nest.desired_environment == EnvironmentDesiredState(
        lights_on=False,
        quiet_mode=True,
    )

    nest.clear_environment_override()
    assert nest.desired_environment == EnvironmentDesiredState(
        lights_on=True,
        quiet_mode=False,
    )
