"""Content collections and right-sidebar review scopes for saved design objects."""

import copy
from typing import Any, Optional

from devtools.asset_design.catalog import Asset


def collection(obj: dict) -> tuple[str, str, str]:
    identifier = obj["id"]
    if identifier.startswith("layout:central"):
        return "layout:central", "主楼布置", "layout"
    if identifier.startswith("layout:terrace"):
        return "layout:terraces", "露台活动布置", "layout"
    if identifier == "layout:pod":
        return identifier, "小屋卧室布置", "layout"
    if identifier == "layout:kit" or identifier.startswith("part:"):
        return "layout:kit", "床桌椅套装", "kit"
    return identifier, obj["label"], obj["group"]


def historical_collection(
    category: str, records: list[dict]
) -> tuple[str, str, str, bool]:
    modules = {record.get("module") for record in records}
    furnished = any(
        record.get("furniture") or record.get("role") == "furniture"
        for record in records
    )
    shell = any(
        record.get("module")
        and not record.get("furniture")
        and record.get("role") != "furniture"
        for record in records
    )
    if category == "central" or (
        "central" in modules and category not in {"pod", "room", "early"}
    ):
        identifier = "building:central" if shell else "layout:central"
    elif category in {"pod", "room", "early"}:
        identifier = "building:pod" if shell else "layout:pod"
    elif any(str(module).startswith("M") for module in modules):
        identifier = (
            "layout:terraces"
            if all(record.get("floor") == 2 for record in records)
            else "layout:pod"
        )
    else:
        identifier = "layout:kit"
    labels = {
        "building:central": "主楼",
        "building:pod": "小屋",
        "layout:central": "主楼布置",
        "layout:pod": "小屋卧室布置",
        "layout:terraces": "露台活动布置",
        "layout:kit": "床桌椅套装",
    }
    group = (
        "building"
        if identifier.startswith("building:")
        else "kit"
        if identifier == "layout:kit"
        else "layout"
    )
    return identifier, labels[identifier], group, shell and furnished


def organize(objects: dict[str, dict]) -> list[dict]:
    for obj in objects.values():
        if not obj.get("historical"):
            obj["collection"], obj["collectionLabel"], obj["group"] = collection(obj)
    for identifier, label in (
        ("layout:central", "主楼布置"),
        ("layout:terraces", "露台活动布置"),
    ):
        members = [
            obj
            for obj in objects.values()
            if obj["collection"] == identifier and not obj.get("historical")
        ]
        if not members:
            continue
        aggregate = {
            **members[0],
            "id": identifier,
            "label": label,
            "module": "central" if identifier == "layout:central" else "",
            "floor": "",
            "aggregate": True,
            "versions": [],
        }
        versions: dict[str, dict[str, Any]] = {}
        for member in members:
            for version in member["versions"]:
                merged = versions.setdefault(
                    version["id"], {**copy.deepcopy(version), "nodes": []}
                )
                merged["nodes"] = sorted(set(merged["nodes"]) | set(version["nodes"]))
        aggregate["versions"] = list(versions.values())
        objects[identifier] = aggregate
    return list(objects.values())


def review_scopes(objects: dict[str, dict], obj: dict) -> Optional[dict]:
    if obj.get("historical"):
        return None
    family = obj["collection"]
    axis = {
        "layout:central": "floor",
        "layout:terraces": "module",
        "layout:kit": "part",
    }.get(family)
    if not axis:
        return None
    choices = []
    for candidate in objects.values():
        if candidate["collection"] != family or candidate.get("historical"):
            continue
        value = (
            candidate["floor"]
            if axis == "floor"
            else candidate["module"]
            if axis == "module"
            else candidate["id"]
        )
        label = (
            candidate["floor"] + " 楼"
            if axis == "floor" and candidate["floor"]
            else candidate["module"]
            if axis == "module" and candidate["module"]
            else candidate["label"]
        )
        if candidate.get("aggregate"):
            label, value = (
                ("全部楼层（查看）" if axis == "floor" else "全部露台（查看）"),
                "all",
            )
        choices.append({"id": candidate["id"], "value": value or "all", "label": label})
    choices.sort(key=lambda entry: (entry["id"] != family, entry["value"]))
    return {"axis": axis, "object": obj["id"], "choices": choices}


def reference_needed(obj: dict, candidate: dict) -> bool:
    if (
        candidate.get("aggregate")
        or candidate.get("historical")
        or obj.get("historical")
    ):
        return False
    family, other = obj["collection"], candidate["collection"]
    if family == "building:central":
        return other == "layout:central" and candidate["space"] == obj["space"]
    if family == "building:pod":
        return (
            other in {"layout:pod", "layout:terraces"}
            and candidate["space"] == obj["space"]
        )
    if family == "layout:central":
        return other == "building:central" and candidate["space"] == obj["space"]
    if family in {"layout:pod", "layout:terraces"}:
        return other == "building:pod" and candidate["space"] == obj["space"]
    return obj["id"].startswith("part:") and candidate["id"] == "layout:kit"


def house_placements(shell: list[dict], houses: list[str]) -> dict[str, int]:
    if not houses:
        return {}
    candidates = sorted(
        (r for r in shell if r.get("module") == houses[0]),
        key=lambda r: (
            "sculpted continuous shell" not in r.get("source_name", r["name"])
        ),
    )
    for anchor in candidates:
        key = anchor.get("source_name", anchor["name"])
        matches: dict[str, Optional[int]] = {
            module: next(
                (
                    r["node"]
                    for r in shell
                    if r.get("module") == module
                    and r.get("source_name", r["name"]) == key
                ),
                None,
            )
            for module in houses
        }
        if all(value is not None for value in matches.values()):
            return {
                module: value for module, value in matches.items() if value is not None
            }
    return {}


def add_version(
    objects: dict[str, dict],
    obj_id: str,
    label: str,
    group: str,
    asset: Asset,
    file: str,
    records: list[dict],
    digest: str,
    space: str,
    module: str = "",
    floor: str = "",
) -> None:
    if not records:
        return
    obj = objects.setdefault(
        obj_id,
        {
            "id": obj_id,
            "label": label,
            "group": group,
            "space": space,
            "module": module,
            "floor": floor,
            "versions": [],
        },
    )
    # A source version stays identifiable even when several exports share its file.
    if any(v["id"] == asset.id for v in obj["versions"]):
        return
    obj["versions"].insert(
        0,
        {
            "id": asset.id,
            "asset": asset.id,
            "title": asset.title,
            "file": file,
            "digest": digest,
            "nodes": sorted(r["node"] for r in records),
            "measurements": asset.measurements,
        },
    )


def can_confirm(obj: Optional[dict]) -> bool:
    return bool(
        obj
        and obj["group"] != "overview"
        and not obj.get("aggregate")
        and not obj.get("historical")
    )
