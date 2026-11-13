"""Formal assets remain exportable while the bedroom workfile stays authoring-only."""

import json
from fnmatch import fnmatch
from pathlib import Path

from infrastructure.godot.artifacts.export_boundary import (
    GODOT_EXPORT_EXCLUDED_PATHS,
    runtime_source_files,
)

GODOT = Path(__file__).resolve().parents[2] / "godot_project"
BEDROOM = GODOT / "nest/furniture/shared/bedroom"


def test_bedroom_keeps_one_authoring_workfile():
    source = BEDROOM / "source"
    assert set(source.iterdir()) == {source / ".gdignore", source / "bedroom.blend"}
    assert (source / "bedroom.blend").stat().st_size > 0
    assert not set(source.iterdir()) & set(runtime_source_files(GODOT))
    assert not (GODOT / "tools/nest_authoring/bedroom-pilot").exists()


def test_formal_bedroom_and_shared_texture_stay_in_export_scope():
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


def test_spatial_receipt_uses_current_source_directories():
    receipt = json.loads((GODOT / "nest/assembly/runtime-inputs.json").read_text())
    assert "nest/spatial/estate_physics.gd" in receipt["files"]
    assert "nest/rendering/estate_lighting.gd" in receipt["files"]
    assert not any(
        path.startswith(
            (
                "tools/",
                "nest/estate/",
                "nest/ui/",
                "nest/furniture/bedroom/",
                "nest/layouts/",
            )
        )
        or "/source/" in path
        for path in receipt["files"]
    )
