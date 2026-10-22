"""Object revisions and their carried copies; originals remain in the catalog."""

import json
import struct
from typing import Any

from devtools.asset_design.design_models import read_model
from devtools.asset_design.object_content import content_digest


def independent_versions(root, objects, issues):
    state_path = root / ".design-adoptions.json"
    current = (
        json.loads(state_path.read_text())["current"] if state_path.exists() else {}
    )
    for obj in objects.values():
        if obj.get("historical") or obj["id"] == "overview":
            # Keep source records intact; the menu folds equal full models.
            for version in obj["versions"]:
                if not version.get("file"):
                    continue
                try:
                    key = content_digest(root, version["file"], version["nodes"])
                    if read_model(root, version["file"])[1] != version["digest"]:
                        raise ValueError("Source changed during object inspection")
                    version["contentDigest"] = key
                except (
                    OSError,
                    ValueError,
                    KeyError,
                    IndexError,
                    struct.error,
                ) as error:
                    issues.append(
                        {
                            "object": obj["id"],
                            "asset": version["asset"],
                            "reason": str(error),
                        }
                    )
            continue
        groups: dict[str, list[dict[str, Any]]] = {}

        # Catalog entries may be prepended or appended. A new carried copy must
        # not become the oldest source merely because it was inserted first.
        def saved_at(version):
            return (root / version["file"]).stat().st_mtime_ns

        for version in sorted(obj["versions"], key=lambda v: (saved_at(v), v["id"])):
            try:
                key = content_digest(root, version["file"], version["nodes"])
                if read_model(root, version["file"])[1] != version["digest"]:
                    raise ValueError("Source changed during object inspection")
            except (ValueError, KeyError, IndexError, struct.error) as error:
                issues.append(
                    {
                        "object": obj["id"],
                        "asset": version["asset"],
                        "reason": str(error),
                    }
                )
                continue
            version["contentDigest"] = key
            groups.setdefault(key, []).append(version)
        versions = []
        adopted = current.get(obj["id"], {})
        for number, copies in enumerate(groups.values(), 1):
            selected = next(
                (v for v in copies if v["id"] == adopted.get("version")), copies[0]
            )
            sources = [
                {
                    "asset": v["asset"],
                    "file": v["file"],
                    "digest": v["digest"],
                    "title": v["title"],
                    "savedAtNs": saved_at(v),
                    "classification": "first-observed"
                    if index == 0
                    else "carried-copy",
                }
                for index, v in enumerate(copies)
            ]
            versions.append(
                {
                    **selected,
                    "title": f"{obj['label']} · V{number:03d}",
                    "sources": sources,
                    "revision": number,
                }
            )
        obj["versions"] = list(reversed(versions))
