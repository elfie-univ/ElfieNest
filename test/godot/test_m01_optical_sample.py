"""The optical experiment must stay isolated from the complete estate."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "godot_project"


def test_m01_is_selected_before_world_or_actor_startup() -> None:
    main = (ROOT / "main.gd").read_text().split("func _ready() -> void:", 1)[1]
    assert main.index("M01_SAMPLE.is_requested()") < main.index(
        "SPECIES_CATALOG.discover_actor_scenes()"
    )
    nest = (ROOT / "rooms/nest.gd").read_text().split("func _ready() -> void:", 1)[1]
    assert nest.index("M01_SAMPLE.is_requested()") < nest.index(
        'call_deferred("rebuild")'
    )


def test_sample_keeps_source_geometry_and_colors() -> None:
    source = (ROOT / "runtime/lab/m01_optical_sample.gd").read_text()
    assert 'extras.get("module", "") != "M01"' in source
    assert 'surface["lods"] = []' in source
    assert "Viewport.MSAA_4X" in source
    assert 'source.get_meta("m01_reference_optics"' in source
    assert '"source_albedo", original.albedo_color' in source
    assert "albedo_color =" not in source
    assert "ESTATE_PHYSICS" not in source
    assert "instances.bin" not in source


def test_sample_metadata_does_not_change_production_optics_contract() -> None:
    importer = (ROOT / "scripts/tools/import_estate_optics.gd").read_text()
    assert 'set_meta("m01_reference_optics"' in importer
    production = (ROOT / "rooms/estate/estate_daylight.gd").read_text()
    assert "m01_reference_optics" not in production


def test_sample_has_real_native_fixture() -> None:
    assert (ROOT / "scripts/test/test_m01_optical_sample.gd").is_file()
