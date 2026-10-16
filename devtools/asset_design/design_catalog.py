"""Project saved scene tags into independently reviewable objects; never edit assets."""

import re
import struct
from functools import partial
from pathlib import Path

from devtools.asset_design.catalog import load_catalog
from devtools.asset_design.design_groups import (
    add_version,
    house_placements,
    organize,
)
from devtools.asset_design.design_history import add_history
from devtools.asset_design.design_models import read_model
from devtools.asset_design.object_versions import independent_versions

GROUPS = {
    "overview": "园区总览",
    "building": "建筑本体",
    "layout": "家具布置",
    "kit": "家具套装",
    "landscape": "室外环境",
}
PART_NAMES = {
    "bed": "床体",
    "bedding": "床品",
    "pillows": "枕头",
    "chair": "椅子",
    "desk": "桌柜",
    "rug": "地毯",
    "lamp": "灯具",
}


def module_name(module):
    return "主楼" if module == "central" else "小屋 " + module


def inventory(root: Path, *, independent: bool = True) -> dict:
    from devtools.asset_design.object_registry import object_inventory

    assets = load_catalog(root).assets
    if any(asset.designObject for asset in assets):
        return object_inventory(root, assets)
    return legacy_inventory(root, independent=independent)


def legacy_inventory(root: Path, *, independent: bool = True) -> dict:
    objects = {
        "overview": {
            "id": "overview",
            "label": "完整园区",
            "group": "overview",
            "space": "archive",
            "module": "",
            "floor": "",
            "versions": [],
        }
    }
    issues = []
    assets = load_catalog(root).assets

    add = partial(add_version, objects)

    estate_ids = {a.id for a in assets if a.category == "estate"}
    for asset in assets:
        file = asset.primaryModel or next(iter(asset.models), None)
        if not file:
            if any(f.kind == "source" for f in asset.files):
                add_history(objects, asset)
            continue
        if not any(f.path == file and f.kind == "model" for f in asset.files):
            continue
        try:
            records, digest = read_model(root, file)
        except (OSError, ValueError, KeyError, IndexError, struct.error) as error:
            issues.append({"object": asset.id, "reason": str(error)})
            continue
        content = [r for r in records if not r.get("reference")]
        if asset.category == "estate":
            add(
                "overview",
                "完整园区",
                "overview",
                asset,
                file,
                records,
                digest,
                "archive",
            )
        elif not add_history(objects, asset, file, records, digest):
            continue
        world = asset.category == "estate" or (
            asset.category == "furniture" and asset.id.split("__")[0] in estate_ids
        )
        space = "estate" if world else "sample:" + asset.category
        modules = sorted(
            {
                r["module"]
                for r in content
                if r.get("module") == "central"
                or re.fullmatch(r"M\d{2}", str(r.get("module", "")))
            }
        )
        if len(modules) == 1:
            content = [
                {**r, "module": modules[0]}
                if r.get("role") == "furniture" and not r.get("module")
                else r
                for r in content
            ]

        def furniture(record):
            return bool(record.get("furniture") or record.get("role") == "furniture")

        def landscape(record):
            return record.get("design_role", record.get("role")) in {
                "landscape",
                "environment",
            } or record.get("module") in {"garden", "landscape", "environment"}

        houses = [m for m in modules if m != "central"]
        template = houses[0] if houses else ""
        placements = house_placements(
            [r for r in content if not furniture(r) and not landscape(r)], houses
        )
        for module in modules if world else []:
            if module != "central" and (
                module != template or asset.category != "estate"
            ):
                continue
            suffix = "central" if module == "central" else "pod"
            label = "主楼" if module == "central" else "小屋"
            shell = [
                r
                for r in content
                if r.get("module") == module and not furniture(r) and not landscape(r)
            ]
            add(
                "building:" + suffix,
                label,
                "building",
                asset,
                file,
                shell,
                digest,
                space,
                module,
            )
            placed = [r for r in content if r.get("module") == module and furniture(r)]
            if module == "central":
                for floor in sorted({str(r.get("floor", 1)) for r in placed}):
                    add(
                        "layout:central:" + floor,
                        "主楼 · " + floor + " 楼",
                        "layout",
                        asset,
                        file,
                        [r for r in placed if str(r.get("floor", 1)) == floor],
                        digest,
                        space,
                        module,
                        floor,
                    )
            else:
                add(
                    "layout:pod",
                    "小屋卧室布置",
                    "layout",
                    asset,
                    file,
                    [r for r in placed if str(r.get("floor", 1)) == "1"],
                    digest,
                    space,
                    module,
                )
                for object_id in ("building:pod", "layout:pod"):
                    for saved in objects.get(object_id, {}).get("versions", []):
                        if saved["id"] == asset.id:
                            saved["placements"] = placements
                            saved["instanceCount"] = len(houses)
        if world:
            for house in houses:
                upper = [
                    r
                    for r in content
                    if r.get("module") == house
                    and furniture(r)
                    and str(r.get("floor", 1)) == "2"
                ]
                add(
                    "layout:terrace:" + house,
                    house + " 露台布置",
                    "layout",
                    asset,
                    file,
                    upper,
                    digest,
                    space,
                    house,
                    "2",
                )
        environment = [r for r in content if landscape(r)]
        if asset.category in {"landscape", "environment"}:
            environment = content
            space = "estate"
        add(
            "landscape:site",
            "庭院与花园",
            "landscape",
            asset,
            file,
            environment,
            digest,
            space,
        )
        if asset.category == "furniture" and not modules:
            if len({r.get("assembly") for r in content} - {None, ""}) > 1:
                add(
                    "layout:kit",
                    "床桌椅套装",
                    "kit",
                    asset,
                    file,
                    content,
                    digest,
                    "kit",
                )
            parts = {
                re.sub(r"_drawer_\d+$", "", str(r.get("assembly", ""))) for r in content
            } - {""}
            for part in sorted(parts):
                add(
                    "part:" + part,
                    PART_NAMES.get(part, part),
                    "kit",
                    asset,
                    file,
                    [
                        r
                        for r in content
                        if re.sub(r"_drawer_\d+$", "", str(r.get("assembly", "")))
                        == part
                    ],
                    digest,
                    "kit",
                )
    order = {asset.id: index for index, asset in enumerate(assets)}
    grouped = organize(objects)
    if independent:
        independent_versions(root, objects, issues)
    for obj in grouped:
        if not independent or obj.get("historical") or obj["id"] == "overview":
            obj["versions"].sort(
                key=lambda version: order[version["asset"]], reverse=True
            )
        if independent and obj.get("aggregate"):
            for number, version in enumerate(reversed(obj["versions"]), 1):
                version["title"] = f"{obj['label']} · 历史组合 {number:03d}（查看）"
    ordered = sorted(grouped, key=lambda o: (list(GROUPS).index(o["group"]), o["id"]))
    return {"objects": ordered, "issues": issues}
