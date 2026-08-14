"""Contracts for the dual-mode Godot Runtime source project."""

from pathlib import Path

from infrastructure.godot.artifacts.export_boundary import (
    GODOT_AUTHORING_ONLY_FILES,
    GODOT_EXPORT_EXCLUDE_FILTER,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GODOT_ROOT = PROJECT_ROOT / "godot_project"


def test_main_scene_does_not_require_a_warmed_global_script_class_cache() -> None:
    # Given: headless validation starts from a clean Godot script-class cache.
    main_source = (GODOT_ROOT / "main.gd").read_text(encoding="utf-8")

    # When: the main scene resolves its preloaded runtime mode helper.
    # Then: it does not require the helper's global class registration to parse.
    assert "var _runtime_mode: ElfieNestRuntimeMode" not in main_source


def test_runtime_modes_do_not_ship_the_retired_jpeg_camera_bridge() -> None:
    # Given: the Runtime has Observer and authority display modes.
    main_source = (GODOT_ROOT / "main.gd").read_text(encoding="utf-8")

    # When: product scene resources are inspected.
    # Then: no fixed-view/frame-loop bridge remains to compete with Observer.
    assert not (GODOT_ROOT / "camera_stream_bridge.gd").exists()
    assert "CameraStreamBridge" not in main_source
    assert "ELFIENEST_GODOT_CAMERA_TOKEN" not in main_source


def test_observer_web_mode_keeps_the_same_origin_ready_signal_without_camera_upload() -> (
    None
):
    # Given: a Web observer waits for the established iframe readiness signal.
    main_source = (GODOT_ROOT / "main.gd").read_text(encoding="utf-8")
    # When: the observer mode completes startup.
    # Then: it posts the existing same-origin signal without a JPEG compatibility path.
    assert "requires_web_ready_signal()" in main_source
    assert "postMessage('elfienest:godot-web-ready', window.location.origin)" in (
        main_source
    )
    assert "/api/godot-camera" not in main_source


def test_authority_semantic_replay_uses_the_shared_godot_event_path() -> None:
    # Given: the dual authority hosts need a parity fixture.
    main_source = (GODOT_ROOT / "main.gd").read_text(encoding="utf-8")

    # When: runtime controller events reach the WebSocket boundary.
    # Then: production and the fixture share the GDScript semantic projection.
    assert (
        GODOT_ROOT / "runtime" / "endpoint" / "authority_semantic_events.gd"
    ).is_file()
    assert (
        GODOT_ROOT / "scripts" / "test" / "test_authority_semantic_replay.gd"
    ).is_file()
    assert "AUTHORITY_SEMANTIC_EVENTS" in main_source
    assert "_semantic_events.project(" in main_source
    assert not (PROJECT_ROOT / "godot_runtime" / "semantic_replay.py").exists()


def test_main_delegates_lab_bridge_behavior_to_a_dedicated_runtime() -> None:
    # Given: main.gd owns startup coordination, not browser-lab details.
    main_source = (GODOT_ROOT / "main.gd").read_text(encoding="utf-8")

    # When: either Lab mode starts.
    # Then: its bridge implementation lives in the dedicated runtime resource.
    assert (GODOT_ROOT / "runtime" / "lab" / "lab_runtime.gd").is_file()
    assert "LAB_RUNTIME" in main_source
    assert "_lab_runtime.setup_elfie_lab()" in main_source
    assert "_lab_runtime.setup_nest_lab()" in main_source
    assert "func _handle_lab_message" not in main_source


def test_export_presets_define_one_web_and_one_linux_dedicated_runtime() -> None:
    # Given: the project export presets.
    presets = (GODOT_ROOT / "export_presets.cfg").read_text(encoding="utf-8")

    # When: build tooling selects Runtime exports.
    # Then: Web is singular and Dedicated is Linux x64/headless only.
    assert presets.count('name="Web"') == 1
    assert 'name="Linux Dedicated"' in presets
    assert 'platform="Linux/X11"' in presets
    assert "dedicated_server=true" in presets
    assert 'binary_format/architecture="x86_64"' in presets
    assert "godot-linux-dedicated/ElfieNestRuntime" in presets


def test_godot_exports_exclude_developer_and_authoring_inputs() -> None:
    presets = (GODOT_ROOT / "export_presets.cfg").read_text(encoding="utf-8")
    assert presets.count(f'exclude_filter="{GODOT_EXPORT_EXCLUDE_FILTER}"') == 2
    for relative in GODOT_AUTHORING_ONLY_FILES:
        path = GODOT_ROOT / relative
        assert path.is_file(), relative
        runtime_sources = tuple(
            candidate
            for candidate in (GODOT_ROOT / "runtime").rglob("*")
            if candidate.is_file()
        ) + (GODOT_ROOT / "main.gd",)
        assert all(
            f"res://{relative}" not in candidate.read_text(encoding="utf-8")
            for candidate in runtime_sources
            if candidate.suffix in {".gd", ".tscn"}
        ), relative
    assert not any(
        path.name.endswith(".import")
        for path in (GODOT_ROOT / "characters").rglob("*.import")
        if "source" in path.parts
    )
