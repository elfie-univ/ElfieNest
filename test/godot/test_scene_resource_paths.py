"""验证 Godot 场景目录和资源引用保持在正式结构内。"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GODOT_ROOT = PROJECT_ROOT / "godot_project"

EXPECTED_SCENES = (
    "main.tscn",
    "rooms/nest.tscn",
    "rooms/activity_room.tscn",
    "rooms/dorm_room.tscn",
    "rooms/portal_room.tscn",
    "rooms/common_area_layouts/kitchen_layout.tscn",
    "rooms/common_area_layouts/sitting_layout.tscn",
    "rooms/common_area_layouts/media_layout.tscn",
    "rooms/common_area_layouts/gym_layout.tscn",
    "rooms/common_area_layouts/garden_layout.tscn",
    "rooms/common_area_layouts/working_layout.tscn",
    "rooms/common_area_layouts/music_layout.tscn",
    "rooms/common_area_layouts/bookroom_layout.tscn",
    "characters/dog/dog.tscn",
    "characters/fox/fox.tscn",
)

EXPECTED_LAYOUTS = {
    Path(path).name
    for path in EXPECTED_SCENES
    if path.startswith("rooms/common_area_layouts/")
}

LEGACY_RESOURCE_PREFIXES = (
    "res://modular_rooms/",
    "res://room/",
    "res://character/",
)


def _source_files() -> list[Path]:
    return [
        path
        for path in GODOT_ROOT.rglob("*")
        if path.is_file()
        and ".godot" not in path.parts
        and path.suffix in {".gd", ".tscn", ".tres", ".import", ".godot"}
    ]


def test_expected_scene_structure_exists() -> None:
    missing = [path for path in EXPECTED_SCENES if not (GODOT_ROOT / path).is_file()]
    assert missing == [], f"缺少正式 Godot 场景: {missing}"


def test_common_area_layout_names_are_exact() -> None:
    layout_root = GODOT_ROOT / "rooms" / "common_area_layouts"
    actual_layouts = {path.name for path in layout_root.glob("*.tscn")}
    assert actual_layouts == EXPECTED_LAYOUTS


def test_legacy_resource_paths_are_not_referenced() -> None:
    stale_references: list[str] = []
    for source_path in _source_files():
        text = source_path.read_text(encoding="utf-8")
        for prefix in LEGACY_RESOURCE_PREFIXES:
            if prefix in text:
                relative_path = source_path.relative_to(PROJECT_ROOT)
                stale_references.append(f"{relative_path}: {prefix}")

    assert stale_references == [], "仍有旧资源路径:\n" + "\n".join(stale_references)


def test_project_uses_main_scene() -> None:
    project_text = (GODOT_ROOT / "project.godot").read_text(encoding="utf-8")
    assert 'run/main_scene="res://main.tscn"' in project_text


def test_runtime_source_declares_protocol_v2_manifest_contract() -> None:
    main_text = (GODOT_ROOT / "main.gd").read_text(encoding="utf-8")
    nest_text = (GODOT_ROOT / "rooms" / "nest.gd").read_text(encoding="utf-8")
    world_controller_text = (GODOT_ROOT / "runtime" / "world_controller.gd").read_text(
        encoding="utf-8"
    )

    assert "const GODOT_PROTOCOL_VERSION := 2" in main_text
    assert '"scene_manifest"' in world_controller_text
    assert '"world_ready"' in world_controller_text
    assert "match command_name:" in main_text
    assert '"configure_world"' in main_text
    assert "func scene_manifest() -> Dictionary:" in nest_text
    assert "func apply_world_config(config: Dictionary) -> Dictionary:" in nest_text


def test_runtime_manifest_is_semantic_and_does_not_export_coordinates() -> None:
    nest_text = (GODOT_ROOT / "rooms" / "nest.gd").read_text(encoding="utf-8")
    manifest_section = nest_text.split("func scene_manifest()", maxsplit=1)[1]
    manifest_section = manifest_section.split(
        "func _build_semantic_anchor_markers",
        maxsplit=1,
    )[0]

    assert '"zones": _semantic_zones(room_count)' in manifest_section
    assert '"anchors": _semantic_anchors(room_count)' in manifest_section
    assert "Vector3" not in manifest_section
    assert '"position"' not in manifest_section


def test_blender_authoring_sources_are_excluded_from_godot_imports() -> None:
    authoring_roots = {
        path.parent for path in GODOT_ROOT.glob("characters/*/source/**/*.blend")
    }

    missing_markers = [
        str(path.relative_to(PROJECT_ROOT))
        for path in sorted(authoring_roots)
        if not (path / ".gdignore").is_file()
    ]

    assert missing_markers == [], (
        f"Blender 制作源目录必须用 .gdignore 与 Godot 自动导入隔离: {missing_markers}"
    )
