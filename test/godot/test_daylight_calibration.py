"""Keep daylight calibration local to rendering, not the approved source asset."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "godot_project"


def test_complete_estate_applies_daylight_before_restoring_shared_instances() -> None:
    source = (ROOT / "rooms/estate/estate_complete_final.gd").read_text()
    ready = source.split("func _ready() -> void:", 1)[1].split("\n\nfunc ", 1)[0]
    assert 'preload("res://rooms/estate/estate_daylight.gd")' in source
    assert ready.index("DAYLIGHT.apply(self)") < ready.index(
        "_restore_instanced_groups()"
    )


def test_daylight_does_not_change_render_quality_or_export_compression() -> None:
    source = (ROOT / "rooms/estate/estate_daylight.gd").read_text()
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
    assert (ROOT / "scripts/test/test_estate_daylight.gd").is_file()


def test_compatibility_light_capacity_covers_the_complete_estate() -> None:
    settings = (ROOT / "project.godot").read_text()
    capacity = re.search(r"^limits/opengl/max_renderable_lights=(\d+)$", settings, re.M)
    assert capacity is not None and int(capacity[1]) >= 215


def test_daylight_uses_reference_ambient_units_and_exposure() -> None:
    scene = (ROOT / "rooms/nest.tscn").read_text()
    assert "ambient_light_energy = 0.2291831181" in scene
    assert "tonemap_mode = 3" in scene
    assert "tonemap_white = 1.0" in scene
    assert "tonemap_exposure = 0.88" in scene


def test_daylight_binds_a_directional_environment_without_replacing_clouds() -> None:
    scene = (ROOT / "rooms/nest.tscn").read_text()
    assert 'path="res://rooms/estate/estate_reflection_sky.gdshader"' in scene
    assert 'type="Sky"' in scene
    assert 'sky = SubResource("Sky_daylight")' in scene
    assert "background_mode = 1" in scene
    assert "ambient_light_source = 2" in scene
    assert "reflected_light_source = 2" in scene


def test_compatibility_sky_does_not_decode_srgb_twice() -> None:
    shader = (ROOT / "rooms/estate/estate_reflection_sky.gdshader").read_text()
    assert "COLOR = color;" in shader
    assert "pow((color + 0.055)" not in shader


def test_authored_warm_bounce_is_not_classified_as_a_powered_lamp() -> None:
    source = (ROOT / "rooms/estate/estate_daylight.gd").read_text()
    assert "_is_authored_bounce" in source
    classifier = source.split("static func _is_artificial(", 1)[1]
    assert "if _is_authored_bounce(material_name):" in classifier
    assert "return false" in classifier


def test_facade_and_observation_glass_use_source_ior_not_default_plastic() -> None:
    source = (ROOT / "rooms/estate/estate_daylight.gd").read_text()
    assert "trial nearly clear ice-aqua facade glass" in source
    assert "metallic_specular" in source
    assert "_glass_specular" in source


def test_interior_fill_does_not_illuminate_the_courtyard() -> None:
    scene = (ROOT / "rooms/nest.tscn").read_text()
    fill = scene.split('[node name="CeilingFill"', 1)[1].split("\n[node ", 1)[0]
    assert "light_cull_mask = 2" in fill
    source = (ROOT / "rooms/estate/estate_daylight.gd").read_text()
    assert "INTERIOR_FILL_LAYER" in source
    restore = (ROOT / "rooms/estate/estate_complete_final.gd").read_text()
    assert "multimesh_instance.layers = 1 | DAYLIGHT.LANDSCAPE_LIGHT_LAYER" in restore


def test_facade_glass_and_shell_do_not_use_interior_fill() -> None:
    source = (ROOT / "rooms/estate/estate_daylight.gd").read_text()
    assert "_uses_interior_fill" in source
    assert "clear observation glass" in source
    assert "TRANSPARENCY_ALPHA" in source
    assert "refraction_enabled = false" in source
    assert "albedo_color.a =" in source


def test_courtyard_review_view_targets_the_building_not_the_sky_bounds() -> None:
    source = (ROOT / "rooms/nest.gd").read_text()
    assert '_register_observation_view("overview", "庭院与建筑"' in source
    assert "overview.global_position = to_global(REFERENCE_REVIEW_POSITION)" in source
    assert "overview.look_at(to_global(REFERENCE_REVIEW_TARGET))" in source
    assert "overview.fov = 38.0" in source


def test_canopy_instances_do_not_use_importer_generated_silhouette_lods() -> None:
    source = (ROOT / "rooms/estate/estate_complete_final.gd").read_text()
    assert "_full_detail_canopy" in source
    assert 'surface["lods"] = []' in source
    assert 'surface["vertex_data"] =' not in source
    assert 'surface["index_data"] =' not in source


def test_full_detail_instances_are_spatially_batched_not_decimated() -> None:
    source = (ROOT / "rooms/estate/estate_complete_final.gd").read_text()
    assert "MAX_BATCH_INSTANCES := 128" in source
    assert "_spatial_batches(instance_buffer)" in source
    assert 'set_meta("source_instance_indices"' in source


def test_authored_fixtures_are_restored_from_asset_local_definitions() -> None:
    source = (ROOT / "rooms/estate/estate_daylight.gd").read_text()
    assert 'extras.get("design_lights", [])' in source
    assert "DAYTIME_FIXTURE_SCALE" in source
    assert 'source.get("target"' in source
    assert "preview_surface_finish" in source


def test_contact_shadows_have_a_furniture_only_caster_mask() -> None:
    scene = (ROOT / "rooms/nest.tscn").read_text()
    assert "shadow_caster_mask = 8" in scene


def test_authored_clearcoat_is_read_from_the_real_glb_not_repainted() -> None:
    source = (ROOT / "rooms/estate/estate_daylight.gd").read_text()
    importer = (ROOT / "scripts/tools/import_estate_optics.gd").read_text()
    assert 'get("KHR_materials_clearcoat"' in importer
    assert 'get("clearcoatFactor"' in importer
    assert "clearcoat_enabled = true" in source
    assert 'get_meta("source_optics"' in source
    assert "FileAccess.open" not in source
    import_settings = (
        ROOT / "rooms/estate/ElfieNest-complete-final.glb.import"
    ).read_text()
    assert (
        'import_script/path="res://scripts/tools/import_estate_optics.gd"'
        in import_settings
    )
