"""Keep placement audit data outside the catalogue's query summary."""

import json
from pathlib import Path
from typing import Optional

from devtools.asset_design.deletion import checked_file, write_bytes


def referenced_reuse_file(
    root: Path, reuse: Optional[dict], version_file: str
) -> Optional[Path]:
    """Validate one owner-local immutable report before publishing any files."""
    if not reuse or "details" not in reuse:
        return None
    root = root.resolve()
    if any(key in reuse for key in ("occurrences", "resources")):
        raise ValueError("Reuse details cannot have both inline and referenced data")
    relative = reuse["details"]
    if not isinstance(relative, str):
        raise ValueError("Invalid reuse details path")
    path = checked_file(root.resolve(), relative)
    if (
        path.name != "reuse.json"
        or path.parent.parent != (root / version_file).parent.parent
    ):
        raise ValueError("Reuse details must belong to the same object's versions")
    data = json.loads(path.read_bytes())
    keys = ("occurrences", "resources")
    if (
        not isinstance(data, dict)
        or "details" in data
        or not any(key in data for key in keys)
        or any(not isinstance(data[key], list) for key in keys if key in data)
    ):
        raise ValueError("Invalid reuse details document")
    return path


def externalize_reuse(root: Path, asset: dict) -> bool:
    """Save immutable revision details while retaining every original value."""
    version = asset.get("designVersion") or {}
    reuse = version.get("reuse")
    if not reuse:
        return False
    referenced = referenced_reuse_file(root, reuse, version["file"])
    if referenced is not None:
        relative = referenced.relative_to(root.resolve()).as_posix()
        if not any(f["path"] == relative for f in asset.get("files", [])):
            asset.setdefault("files", []).append(
                {
                    "path": relative,
                    "name": "reuse.json",
                    "kind": "data",
                    "bytes": referenced.stat().st_size,
                }
            )
        return True
    if not any(key in reuse for key in ("occurrences", "resources")):
        return False
    relative = (Path(version["file"]).parent / "reuse.json").as_posix()
    target = checked_file(root.resolve(), relative)
    data = json.dumps(reuse, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
    if target.exists():
        if target.read_bytes() != data:
            raise ValueError("Saved reuse details differ; nothing overwritten")
    else:
        write_bytes(target, data)
    version["reuse"] = {
        **{
            key: value
            for key, value in reuse.items()
            if key not in {"occurrences", "resources"}
        },
        "details": relative,
    }
    asset.setdefault("files", []).append(
        {"path": relative, "name": "reuse.json", "kind": "data", "bytes": len(data)}
    )
    return True
