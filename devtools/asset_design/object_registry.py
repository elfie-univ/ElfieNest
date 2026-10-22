"""Explicit object ownership; full-scene exports are only import/archive inputs."""

import copy
import json

from devtools.asset_design.design_models import read_model
from devtools.asset_design.object_content import content_digest
from devtools.asset_design.working_drafts import add_working_drafts


def object_inventory(root, assets):
    objects, issues = {}, []
    for asset in assets:
        if not asset.designObject:
            continue
        metadata = asset.designObject
        obj = objects.setdefault(
            metadata["id"],
            {**copy.deepcopy(metadata), "versions": [], "archivedVersions": []},
        )
        version = copy.deepcopy(asset.designVersion)
        if asset.archived and version.get("archiveFile"):
            obj["archivedVersions"].append(version)
            continue
        try:
            records, version["digest"] = read_model(root, version["file"])
            version["nodes"] = [r["node"] for r in records if not r.get("reference")]
            version["contentDigest"] = content_digest(
                root, version["file"], version["nodes"]
            )
        except (OSError, ValueError, KeyError) as error:
            issues.append(
                {"object": obj["id"], "asset": asset.id, "reason": str(error)}
            )
            continue
        obj["archivedVersions" if asset.archived else "versions"].append(version)
    for obj in objects.values():
        obj["versions"].sort(key=lambda v: v["revision"], reverse=True)
    state_path = root / "adoptions.json"
    current = (
        json.loads(state_path.read_text()).get("current", {})
        if state_path.exists()
        else {}
    )
    for identifier, label in (
        ("layout:central", "主楼布置"),
        ("layout:terraces", "露台活动布置"),
    ):
        members = [
            o
            for o in objects.values()
            if o["collection"] == identifier and o["versions"]
        ]
        if not members:
            continue
        selected = []
        for member in members:
            saved = current.get(member["id"], {}).get("version")
            version = next(
                (v for v in member["versions"] if v["id"] == saved),
                member["versions"][0],
            )
            selected.append({"object": member["id"], "version": version["id"]})
        objects[identifier] = {
            **members[0],
            "id": identifier,
            "label": label,
            "aggregate": True,
            "module": "central" if identifier == "layout:central" else "",
            "floor": "",
            "archivedVersions": [],
            "versions": [
                {
                    **members[0]["versions"][0],
                    "id": "composition",
                    "title": label + " · 当前对象组合（查看）",
                    "members": selected,
                }
            ],
        }
    add_working_drafts(root, objects, issues)
    overview = {
        "id": "overview",
        "label": "完整园区",
        "group": "overview",
        "collection": "overview",
        "collectionLabel": "完整园区",
        "space": "estate",
        "module": "",
        "floor": "",
        "versions": [],
    }
    return {
        "objects": [overview, *sorted(objects.values(), key=lambda o: o["id"])],
        "issues": issues,
    }
