"""Authoring pilots stay editable without shipping their duplicate models."""

import json
from fnmatch import fnmatch
from pathlib import Path
from struct import unpack

from infrastructure.godot.artifacts.export_boundary import (
    GODOT_EXPORT_EXCLUDED_PATHS,
    runtime_source_files,
)

GODOT = Path(__file__).resolve().parents[2] / "godot_project"
PILOT = GODOT / "tools/nest_authoring/bedroom-pilot"


def test_bedroom_pilot_models_are_excluded_but_shared_texture_is_retained():
    pilot_files = [path for path in PILOT.rglob("*") if path.is_file()]
    assert (PILOT / "bedroom.tscn").is_file()
    assert sum(path.suffix == ".glb" for path in pilot_files) == 6
    assert sum(path.suffix == ".scn" for path in pilot_files) == 6
    assert sum(path.suffix == ".blend" for path in pilot_files) == 6
    assert all(
        (path.parent / ".gdignore").is_file()
        for path in pilot_files
        if path.suffix == ".blend"
    )
    for path in pilot_files:
        relative = path.relative_to(GODOT).as_posix()
        assert any(
            fnmatch(relative, pattern) for pattern in GODOT_EXPORT_EXCLUDED_PATHS
        )
    assert set(pilot_files).isdisjoint(runtime_source_files(GODOT))
    for relative in (
        "nest/furniture/textures/5b243550b6900cbd2364903857ba1125fb3537f2b32ca438d758b8cc5eccb043.png",
        "nest/furniture/shared/bedroom/bed-shared.glb",
        "nest/furniture/sets/bedroom/bedroom-set-a.scn",
        "nest/furniture/layouts/bedroom/bedroom-layout.scn",
    ):
        assert (GODOT / relative).is_file(), relative
        assert not any(
            fnmatch(relative, pattern) for pattern in GODOT_EXPORT_EXCLUDED_PATHS
        )


def test_bedroom_pilot_scenes_are_discoverable_on_a_clean_godot_import():
    for directory in (PILOT, *PILOT.parents):
        if directory == GODOT:
            break
        assert not (directory / ".gdignore").exists(), directory


def test_bedroom_pilot_glbs_resolve_external_textures():
    texture_root = GODOT / "nest/furniture/textures"
    for glb in PILOT.rglob("*.glb"):
        with glb.open("rb") as stream:
            stream.seek(12)
            size, kind = unpack("<I4s", stream.read(8))
            assert kind == b"JSON", glb
            images = json.loads(stream.read(size)).get("images", [])
        for image in images:
            if "uri" in image:
                texture = (glb.parent / image["uri"]).resolve()
                assert texture.parent == texture_root and texture.is_file(), texture


def test_formal_spatial_receipt_has_no_bedroom_pilot_inputs():
    receipt = json.loads((GODOT / "nest/assembly/runtime-inputs.json").read_text())
    assert not (GODOT / "nest/furniture/bedroom").exists()
    assert not (GODOT / "nest/layouts").exists()
    assert all(
        not path.startswith(
            ("tools/nest_authoring/", "nest/furniture/bedroom/", "nest/layouts/")
        )
        for path in receipt["files"]
    )
