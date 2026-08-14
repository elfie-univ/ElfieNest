"""Single source of truth for Godot source trees excluded from exports."""

from __future__ import annotations

from typing import Final, Tuple

GODOT_EXPORT_EXCLUDED_PATHS: Final[Tuple[str, ...]] = (
    "scripts/*",
    "characters/tools/*",
    "characters/dog/source/*",
    "characters/fox/source/*",
    "rooms/assets/reference/*",
)

GODOT_EXPORT_EXCLUDE_FILTER: Final[str] = ",".join(GODOT_EXPORT_EXCLUDED_PATHS)

# These resources are deliberately kept in source control for authoring or
# reference work.  They are not runtime inputs and must never be exported.
GODOT_AUTHORING_ONLY_PATHS: Final[Tuple[str, ...]] = (
    "characters/fox/source",
    "characters/tools",
    "rooms/assets/reference",
)
GODOT_AUTHORING_ONLY_FILES: Final[Tuple[str, ...]] = (
    "rooms/assets/artwork/framed_picture.tscn",
    "rooms/assets/beds/bed_chair.tscn",
    "rooms/assets/chairs/pc_chair.tscn",
    "rooms/assets/tables/pc_setup.tscn",
    "rooms/assets/tables/pc_table.tscn",
    "rooms/assets/tables/table_small.tscn",
)


def export_boundary_manifest() -> dict[str, object]:
    """Return JSON-safe provenance for generated Runtime build manifests."""
    return {
        "filter": "all_resources",
        "excluded_paths": list(GODOT_EXPORT_EXCLUDED_PATHS),
        "authoring_only_paths": list(GODOT_AUTHORING_ONLY_PATHS),
        "authoring_only_files": list(GODOT_AUTHORING_ONLY_FILES),
    }


__all__ = (
    "GODOT_AUTHORING_ONLY_PATHS",
    "GODOT_AUTHORING_ONLY_FILES",
    "GODOT_EXPORT_EXCLUDED_PATHS",
    "GODOT_EXPORT_EXCLUDE_FILTER",
    "export_boundary_manifest",
)
