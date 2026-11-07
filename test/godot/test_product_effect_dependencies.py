"""Product scene resources must load without the developer Lab implementation."""

import re
from pathlib import Path

GODOT_ROOT = Path(__file__).resolve().parents[2] / "godot_project"


def test_product_scene_dependency_graph_excludes_lab() -> None:
    pending = [
        "nest/nest.tscn",
        "runtime/actor/actor_controller.gd",
        "runtime/observer/observer_presentation.gd",
    ]
    seen = set()
    while pending:
        relative = pending.pop()
        if relative in seen:
            continue
        seen.add(relative)
        assert not relative.startswith("runtime/lab/"), relative
        path = GODOT_ROOT / relative
        if path.suffix not in {".gd", ".tscn", ".tres", ".gdshader"}:
            continue
        assert path.is_file(), relative
        pending.extend(re.findall(r'res://([^"\s]+)', path.read_text()))


def test_main_only_loads_lab_for_explicit_lab_modes() -> None:
    source = (GODOT_ROOT / "main.gd").read_text()
    assert 'preload("res://runtime/lab/' not in source
    assert "if _lab_mode or _nest_lab_mode:\n\t\t_setup_lab_runtime()" in source


def test_product_controllers_have_no_synthetic_wander_path() -> None:
    for relative in (
        "main.gd",
        "runtime/actor/actor_controller.gd",
        "runtime/observer/observer_presentation.gd",
    ):
        source = (GODOT_ROOT / relative).read_text().lower()
        assert "mock_wander" not in source, relative
        assert "mock_motion" not in source, relative


def test_observer_and_nest_models_drop_synthetic_motion() -> None:
    from app.orchestration.nest_session import ObserverSemanticEntity
    from nest.public import RuntimeResidentMirror

    assert "mock_motion" not in ObserverSemanticEntity.model_fields
    assert "mock_motion" not in RuntimeResidentMirror.model_fields
