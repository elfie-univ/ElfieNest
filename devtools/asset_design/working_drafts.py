"""One opt-in mutable source preview per object, outside published history."""

import copy
import json

from devtools.asset_design.catalog import registered_file
from devtools.asset_design.design_models import read_model
from devtools.asset_design.object_content import content_digest
from devtools.asset_design.paths import object_directory


def add_working_drafts(root, objects, issues):
    for obj in objects.values():
        if obj.get("aggregate") or obj.get("historical") or not obj["versions"]:
            continue
        folder = object_directory(root, obj["id"])
        path = folder / "source" / "build.json"
        if not path.is_file():
            continue
        try:
            build = json.loads(path.read_text())
            if build.get("workingDraft") is not True:
                continue
            file = (folder / "source" / "model.glb").relative_to(root).as_posix()
            if registered_file(root, file) is None:
                raise ValueError("Working source is not registered")
            records, digest = read_model(root, file)
            nodes = [r["node"] for r in records if not r.get("reference")]
            content = content_digest(root, file, nodes)
            latest = obj["versions"][0]
            if content == latest["contentDigest"]:
                continue
            obj["versions"].insert(
                0,
                {
                    "id": "draft",
                    "asset": latest["asset"],
                    "title": obj["label"] + " · 工作稿（未编号）",
                    "draft": True,
                    "file": file,
                    "digest": digest,
                    "contentDigest": content,
                    "nodes": nodes,
                    "placements": build.get("placements", {}),
                    "instanceCount": build.get("instanceCount", 0),
                },
            )
        except (OSError, ValueError, KeyError) as error:
            issues.append({"object": obj["id"], "reason": "工作稿：" + str(error)})


def freeze_working_layers(root, layers):
    # Only the selected object may allocate a published revision on confirmation.
    from devtools.asset_design.catalog import load_catalog
    from devtools.asset_design.object_assets import publish_object

    saved = copy.deepcopy(layers)
    for entry in saved:
        if entry.get("reference") or not entry.get("draft"):
            continue
        publish_object(root, entry["object"])
        asset = next(
            a
            for a in reversed(load_catalog(root).assets)
            if a.designObject
            and a.designObject["id"] == entry["object"]
            and a.designVersion["contentDigest"] == entry["contentDigest"]
        )
        entry.update(asset.designVersion)
        entry["version"] = asset.designVersion["id"]
        entry.pop("draft")
    return saved
