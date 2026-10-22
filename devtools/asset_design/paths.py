"""Stable object-owned paths for authored design assets."""

import re
from pathlib import Path

WORK_ROOT = Path(__file__).resolve().parents[2] / "build" / "asset_design"


def object_directory(root: Path, identifier: str) -> Path:
    if not re.fullmatch(r"[a-z]+:[A-Za-z0-9_]+(?::[A-Za-z0-9_]+)?", identifier):
        raise ValueError("Invalid design object: " + identifier)
    parts = identifier.split(":")
    family, name = parts[:2]
    if family == "building" and len(parts) == 2:
        relative = "buildings/" + name
    elif family == "layout" and name == "central" and len(parts) == 3:
        relative = "layouts/central_floor_" + parts[2]
    elif family == "layout" and name == "terrace" and len(parts) == 3:
        relative = "layouts/terraces/" + parts[2]
    elif identifier == "layout:pod":
        relative = "layouts/pod_bedroom"
    elif identifier == "layout:kit":
        relative = "furniture/personal_nook"
    elif family == "part" and len(parts) == 2:
        relative = "furniture/" + name
    elif family == "landscape" and len(parts) == 2:
        relative = "landscape/" + name
    else:
        raise ValueError("Unsupported design object: " + identifier)
    return root / relative


def revision_file(folder: Path, revision: int) -> Path:
    return folder / "versions" / f"v{revision:03d}" / "model.glb"
