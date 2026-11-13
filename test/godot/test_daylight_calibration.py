"""Keep daylight calibration local to rendering, not the approved source asset."""

import hashlib
import json
import re
from pathlib import Path

from test.godot.asset_geometry import read_glb

ROOT = Path(__file__).resolve().parents[2] / "godot_project"


def test_split_estate_restores_all_authored_light_controls() -> None:
    bindings = json.loads((ROOT / "nest/assembly/runtime-bindings.json").read_text())
    lights = bindings["lighting"]["lights"]
    assert len(lights) == 273
    assert all(
        set(control) == {"energy", "group", "mask", "visible"}
        for control in lights.values()
    )
    assert all(
        control["energy"] >= 0 and control["mask"] > 0 and control["group"]
        for control in lights.values()
    )
    source = (ROOT / "nest/assembly/estate_runtime.gd").read_text()
    assert 'const BINDINGS := "res://nest/assembly/runtime-bindings.json"' in source
    assert "restore_lighting(data.lighting)" in source
    assert (
        'restored_controls.lights == find_children("*", "Light3D", true, false).size()'
        in source
    )
    for property in ("light_energy", "light_cull_mask", "visible"):
        assert f"node.{property} =" in source
    scene = (ROOT / "nest/assembly/estate.tscn").read_text()
    assert 'path="res://nest/assembly/estate_runtime.gd"' in scene


def test_daylight_does_not_change_render_quality_or_export_compression() -> None:
    source = (ROOT / "nest/rendering/estate_daylight.gd").read_text()
    assert "set_surface_override_material" in source
    assert "duplicate()" in source
    for forbidden in (
        "albedo_color =",
        "albedo_texture =",
        "roughness =",
        "texture_filter =",
        "lod_bias =",
        "ProjectSettings.set_setting",
    ):
        assert re.search(r"\b" + re.escape(forbidden) + r"(?!=)", source) is None


def test_daylight_has_a_focused_native_behavior_fixture() -> None:
    assert (ROOT / "test/test_estate_daylight.gd").is_file()


def test_compatibility_light_capacity_covers_the_complete_estate() -> None:
    settings = (ROOT / "project.godot").read_text()
    capacity = re.search(r"^limits/opengl/max_renderable_lights=(\d+)$", settings, re.M)
    assert capacity is not None and int(capacity[1]) >= 215


def test_daylight_uses_reference_ambient_units_and_exposure() -> None:
    scene = (ROOT / "nest/nest.tscn").read_text()
    assert "ambient_light_energy = 0.2291831181" in scene
    assert "tonemap_mode = 3" in scene
    assert "tonemap_white = 1.0" in scene
    assert "tonemap_exposure = 0.88" in scene


def test_daylight_binds_a_directional_environment_without_replacing_clouds() -> None:
    scene = (ROOT / "nest/nest.tscn").read_text()
    assert 'path="res://nest/rendering/estate_reflection_sky.gdshader"' in scene
    assert 'type="Sky"' in scene
    assert 'sky = SubResource("Sky_daylight")' in scene
    assert "background_mode = 1" in scene
    assert "ambient_light_source = 2" in scene
    assert "reflected_light_source = 2" in scene


def test_compatibility_sky_does_not_decode_srgb_twice() -> None:
    shader = (ROOT / "nest/rendering/estate_reflection_sky.gdshader").read_text()
    assert "COLOR = environment_color.rgb;" in shader
    assert "night_amount > 0.5 && !AT_CUBEMAP_PASS" in shader
    assert "COLOR = night_sky(normalize(EYEDIR));" in shader
    assert "pow((color + 0.055)" not in shader


def test_authored_warm_bounce_is_not_classified_as_a_powered_lamp() -> None:
    source = (ROOT / "nest/rendering/estate_daylight.gd").read_text()
    assert "_is_authored_bounce" in source
    classifier = source.split("static func _is_artificial(", 1)[1]
    assert "if _is_authored_bounce(material_name):" in classifier
    assert "return false" in classifier


def test_facade_and_observation_glass_use_source_ior_not_default_plastic() -> None:
    source = (ROOT / "nest/rendering/estate_daylight.gd").read_text()
    assert "trial nearly clear ice-aqua facade glass" in source
    assert "metallic_specular" in source
    assert "_glass_specular" in source


def test_observer_does_not_add_an_artificial_ceiling_fill() -> None:
    scene = (ROOT / "nest/nest.tscn").read_text()
    assert '[node name="CeilingFill"' not in scene
    source = (ROOT / "nest/rendering/estate_daylight.gd").read_text()
    receiver = source.split("static func _uses_interior_fill(", 1)[1].split(
        "\nstatic func ", 1
    )[0]
    assert 'str(extras.get("module", "")) != "central"' in receiver
    assert 'int(extras.get("floor", 1)) != 1' in receiver
    assert 'or bool(extras.get("glass", false))' in receiver
    assert "return false" in receiver


def test_facade_glass_and_shell_do_not_use_interior_fill() -> None:
    source = (ROOT / "nest/rendering/estate_daylight.gd").read_text()
    assert "_uses_interior_fill" in source
    assert "clear observation glass" in source
    assert "TRANSPARENCY_ALPHA" in source
    assert "refraction_enabled = false" in source
    assert "albedo_color.a =" in source


def test_courtyard_review_view_targets_the_building_not_the_sky_bounds() -> None:
    source = (ROOT / "nest/nest.gd").read_text()
    assert '_register_observation_view("overview", "全园总览"' in source
    assert "overview.global_position = to_global(REFERENCE_REVIEW_POSITION)" in source
    assert "overview.look_at(to_global(REFERENCE_REVIEW_TARGET))" in source
    assert "overview.fov = 38.0" in source


def test_accepted_split_source_tree_keeps_authored_glb_inputs() -> None:
    # Freeze the accepted split GLBs, including authored geometry and materials.
    manifest = json.loads((ROOT / "nest/assembly/runtime-inputs.json").read_text())
    expected = {
        path: digest
        for path, digest in manifest["files"].items()
        if path.endswith(".glb")
    }
    assert len(expected) == 56
    fingerprint = hashlib.sha256(
        json.dumps(expected, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert (
        fingerprint
        == "72cb35c2501efc41d8c0b6ba1a534b911b4ca97ce534794d4d5a9c5458488d2b"
    )
    actual = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (ROOT / "nest").rglob("*.glb")
    }
    assert actual == expected


def test_shared_placements_keep_actual_source_prototype_identities() -> None:
    index = json.loads((ROOT / "nest/assembly/asset-index.json").read_text())
    entries = index["fileGraph"]["entries"]
    sources = [
        entry["file"] for key, entry in entries.items() if key.startswith("source:")
    ]
    assert len(sources) == len(set(sources)) == 56
    for relative in sources:
        document, _ = read_glb(ROOT / "nest" / relative)
        group_members = {
            child
            for node in document["nodes"]
            if node.get("extras", {}).get("nest_instance_group")
            for child in node.get("children", [])
        }
        nodes = [node for node in document["nodes"] if "mesh" in node]
        assert nodes, relative
        names = [node["name"] for node in nodes if "name" in node]
        assert len(set(names)) == len(names), relative
        for index, node in enumerate(document["nodes"]):
            if "mesh" not in node:
                continue
            assert 0 <= node["mesh"] < len(document["meshes"]), (relative, index)
            extras = node.get("extras", {})
            if index in group_members or extras.get("nest_surface"):
                continue
            assert node["name"] and extras["source_name"] and extras["v044_path"], (
                relative,
                node["name"],
            )
    placement = (ROOT / "nest/assembly/glb_placement.gd").read_text()
    assert "meshes[str(node.name)] = node.mesh" in placement
    assert "target.mesh = mesh" in placement
    assert "batch.mesh = mesh" in placement
    assert "batch.buffer = buffer" in placement
    assert "buffer.size() != data.instance_count * stride" in placement


def test_authored_fixtures_are_restored_from_asset_local_definitions() -> None:
    source = (ROOT / "nest/rendering/estate_daylight.gd").read_text()
    assert 'extras.get("design_lights", [])' in source
    assert "DAYTIME_FIXTURE_SCALE" in source
    assert 'source.get("target"' in source
    assert "preview_surface_finish" in source


def test_contact_shadows_have_a_furniture_only_caster_mask() -> None:
    source = (ROOT / "nest/rendering/estate_daylight.gd").read_text()
    assert "const FURNITURE_CONTACT_LAYER := 8" in source
    contact = source.split("if not outdoor and not contact_rooms.has(room):", 1)[1]
    contact = contact.split("contact_rooms[room] = true", 1)[0]
    assert "light.shadow_caster_mask = FURNITURE_CONTACT_LAYER" in contact
    assert "light.shadow_enabled = true" in contact


def test_authored_clearcoat_is_read_from_the_real_glb_not_repainted() -> None:
    source = (ROOT / "nest/rendering/estate_daylight.gd").read_text()
    importer = (ROOT / "tools/import_estate_optics.gd").read_text()
    assert 'get("KHR_materials_clearcoat"' in importer
    assert 'get("clearcoatFactor"' in importer
    assert "clearcoat_enabled = true" in source
    assert 'get_meta("source_optics"' in source
    assert "FileAccess.open" not in source
    # Split sources use the same current importer policy; calibrated materials
    # are saved on placements rather than re-running the retired whole importer.
    imports = list((ROOT / "nest").rglob("*.glb.import"))
    assert len(imports) == 56
    import_hooks = {
        "bed-shared.glb.import": '"res://tools/import_bed_normal_variants.gd"',
        "forest-foliage.glb.import": '"res://tools/import_foliage_lods.gd"',
    }
    for path in imports:
        assert path.with_suffix("").is_file(), path
        hooks = re.findall(r"^import_script/path=(.*)$", path.read_text(), re.M)
        assert hooks == [import_hooks.get(path.name, '""')], path
