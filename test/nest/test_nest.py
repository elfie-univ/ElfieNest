import pytest

from nest import Nest
from nest.living_rules.errors import (
    BedConflictError,
    NoHomeAvailableError,
    UnknownResidentError,
)
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

    assert (
        nest.queue_semantic_action(
            command_id="home-1",
            actor_id="fox-1",
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
