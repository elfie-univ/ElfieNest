"""Authoring pilots stay editable without shipping their duplicate models."""

from fnmatch import fnmatch

from infrastructure.godot.artifacts.export_boundary import GODOT_EXPORT_EXCLUDED_PATHS


def test_bedroom_pilot_models_are_excluded_but_shared_texture_is_retained():
    for relative in (
        "nest/furniture/bedroom/bed/bed.glb",
        "nest/furniture/bedroom/bed/bed.scn",
        "nest/furniture/bedroom/chair/chair.glb",
        "nest/furniture/bedroom/chair/chair.scn",
        "nest/furniture/bedroom/desks/a/desk_a.glb",
        "nest/furniture/bedroom/desks/d/desk_d.scn",
        "nest/layouts/bedroom/bedroom.tscn",
    ):
        assert any(
            fnmatch(relative, pattern) for pattern in GODOT_EXPORT_EXCLUDED_PATHS
        )
    for relative in (
        "nest/furniture/bedroom/textures/5b243550b6900cbd2364903857ba1125fb3537f2b32ca438d758b8cc5eccb043.png",
        "nest/furniture/shared/bedroom/bed-shared.glb",
        "nest/furniture/sets/bedroom/bedroom-set-a.scn",
        "nest/furniture/layouts/bedroom/bedroom-layout.scn",
    ):
        assert not any(
            fnmatch(relative, pattern) for pattern in GODOT_EXPORT_EXCLUDED_PATHS
        )
