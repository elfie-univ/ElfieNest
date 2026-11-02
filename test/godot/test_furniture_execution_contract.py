"""Static guardrails only; actual collisions/poses require Godot integration tests."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "godot_project"


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_furniture_use_waits_for_navigation_terminal() -> None:
    controller = _source("runtime/actor/actor_controller.gd")
    terminal = controller.split("func _on_actor_navigation_terminal(", 1)[1]
    terminal = terminal.split("\n\nfunc ", 1)[0]
    assert "_pending_anchor_uses" in terminal
    assert 'status == "completed"' in terminal
    assert "enter_furniture" in terminal
    assert '"furniture_occupied"' in controller
    assert '"invalid_use_anchor_payload"' in controller
    assert "_command_actor_ids.has(command_id)" in controller
    assert "_terminal_commands.has(command_id)" in controller


def test_furniture_pose_is_authored_bounded_and_reversible() -> None:
    actor = _source("characters/shared/elfie_actor.gd")
    enter = actor.split("func enter_furniture(", 1)[1].split("\n\nfunc ", 1)[0]
    assert '"interaction_transform"' in enter
    assert '"interaction_posture"' in enter
    assert "FURNITURE_CONTACT_DISTANCE" in enter
    assert "_furniture_exit_transform = global_transform" in enter
    assert "func leave_furniture() -> bool:" in actor
    assert "_furniture_exit_is_clear" in actor
    catalog = _source("runtime/actor/actor_catalog.gd")
    assert "actor_instance.runtime_posture()" in catalog


def test_real_stairs_use_gravity_and_swept_step_clearance() -> None:
    actor = _source("characters/shared/elfie_actor.gd")
    assert "const MAX_STEP_HEIGHT := 0.20" in actor
    assert "get_gravity()" in actor
    assert "func _try_step_up(" in actor
    step = actor.split("func _try_step_up(", 1)[1].split("\n\nfunc ", 1)[0]
    assert "test_move(" in step
    assert "is_floor" not in step  # use swept support, not a stale cached floor flag
    assert "get_floor_max_angle()" in step
    assert "global_position.y =" not in actor


def test_gravity_does_not_change_the_nonphysical_preview() -> None:
    actor = _source("characters/shared/elfie_actor.gd")
    process = actor.split("func _physics_process(", 1)[1].split("\n\nfunc ", 1)[0]
    assert process.index("if install_preview_poses:") < process.index("get_gravity()")


def test_real_action_terminal_publishes_current_world_state() -> None:
    controller = _source("runtime/actor/actor_controller.gd")
    terminal = controller.split("func _emit_terminal(", 1)[1]
    assert terminal.index('runtime_event.emit("intent_terminal"') < terminal.index(
        'runtime_event.emit("world_snapshot", world_snapshot(), command_id)'
    )


def test_observer_action_target_is_an_authoritative_semantic_anchor() -> None:
    catalog = _source("runtime/actor/actor_catalog.gd")
    assert '"action_anchor_id"' in catalog
    assert "actor_instance.furniture_anchor_id" in catalog
    controller = _source("runtime/actor/actor_controller.gd")
    assert 'set_meta("action_anchor_id", anchor_id)' in controller
