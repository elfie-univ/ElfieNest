import pytest

from nest import Nest, NestConfig, NestFullError
from nest.engine import InvalidTickError


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


def test_nest_capacity_rejects_an_extra_resident() -> None:
    # Given
    nest = Nest(NestConfig(max_residents=1))
    nest.register_resident("elfie-1")

    # When / Then
    with pytest.raises(NestFullError, match="1/1"):
        nest.register_resident("elfie-2")


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


def test_furniture_occupancy_moves_with_resident() -> None:
    # Given
    nest = Nest()
    nest.register_resident("elfie-1")
    nest.register_scene_furniture(("bed-1", "chair-1"))

    # When
    nest.update_resident_posture("elfie-1", "lying", "bed-1")
    nest.update_resident_posture("elfie-1", "sitting", "chair-1")

    # Then
    assert nest.state.furniture["bed-1"].occupant_id is None
    assert nest.state.furniture["chair-1"].occupant_id == "elfie-1"


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
