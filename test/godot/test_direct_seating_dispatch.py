"""All seating commands use the same authored direct landing and exit."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACTOR = ROOT / "godot_project/runtime/actor"


def test_every_seat_dispatches_to_direct_cycle_without_species_or_anchor_gate():
    source = (ACTOR / "furniture_cycle.gd").read_text()
    seating = source.split('if variant != "seat"', 1)[1].split("func _stage", 1)[0]
    assert "direct_seat_cycle.gd" in seating
    assert "species_id" not in seating
    assert "dorm-01/chair-01" not in seating
    assert "_seat(marker" not in source
    assert "_bench(marker" not in source


def test_retired_mount_and_stand_chains_are_removed():
    source = (ACTOR / "chair_clip_sequence.gd").read_text()
    for name in ["Stand To Sit", "Sit To Stand", "Step Onto Platform", "Jump Down"]:
        assert name not in source
        assert not (
            ROOT / "godot_project/characters/animation/candidates" / (name + ".fbx")
        ).exists()
    assert not (ACTOR / "furniture_motion_plan.gd").exists()
