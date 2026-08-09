import pytest

from nest import Nest
from nest.engine import InvalidTickError
from nest.state.store import (
    BedConflictError,
    NoHomeAvailableError,
    UnknownResidentError,
)


def _catalog_with_beds(count: int):
    from nest.state.models import (
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


def test_broadcast_reaches_other_active_residents_only() -> None:
    # Given
    nest = Nest()
    nest.register_resident("elfie-1")
    nest.register_resident("elfie-2")

    # When
    nest.broadcast_speech("elfie-1", "一起去活动区")

    # Then
    assert nest.consume_sensory_input("elfie-1") == ""
    assert "一起去活动区" in nest.consume_sensory_input("elfie-2")
    assert nest.consume_sensory_input("elfie-2") == ""


def test_nest_keeps_semantic_posture_without_copying_godot_furniture() -> None:
    nest = Nest()
    nest.register_resident("elfie-1")

    nest.update_resident_posture("elfie-1", "sitting")

    resident = nest.resident_state("elfie-1")
    assert resident is not None and resident.posture == "sitting"
    assert not hasattr(nest.state, "furniture")


def test_nest_tick_advances_environment_without_an_elfie_instance() -> None:
    # Given
    nest = Nest()

    # When
    nest.tick(1.5)

    # Then
    assert nest.state.elapsed_seconds == 1.5


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


def test_nest_catalog_shrink_marks_reconciliation_required() -> None:
    # Given
    nest = Nest()
    nest.apply_catalog(_catalog_with_beds(2))
    nest.admit_resident("fox-1")

    # When
    nest.apply_catalog(_catalog_with_beds(0))

    # Then
    assert nest.state.reconciliation_required is True
    assert nest.home_anchor_id("fox-1") == "dorm-01/bed-01"


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
    assert nest.state.elapsed_seconds == 5.0
