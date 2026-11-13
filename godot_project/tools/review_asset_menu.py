"""Apply the GLB source / SCN assembly boundary to the Nest review menu."""

from collections import defaultdict

from export_menu_assets import DESK_IDS, DESK_LIBRARY
from review_asset_relationships import add_reverse_links, build_relationships

DESK_FILE_ID = f"source:{DESK_LIBRARY}"


def leaf(key, entries):
    return {"id": key, "label": entries[key]["title"]}


def section(section_id, label, children):
    return {"id": section_id, "label": label, "children": children}


def catalog_leaves(items):
    for item in items:
        if "children" in item:
            yield from catalog_leaves(item["children"])
        else:
            yield item


def add_desks(entries, plan, inventory):
    views = {view["id"]: view for view in plan["views"]}
    nodes = {node["path"]: node for node in inventory}
    owners = plan["geometry"]
    mesh_at = plan["mesh_at_path"]

    def desk_shape(path):
        shape = mesh_at.get(path)
        return shape is not None and owners[shape]["asset"] in DESK_IDS

    for asset in DESK_IDS:
        paths = [path for path in views[asset]["paths"] if desk_shape(path)]
        assert len(paths) == 9, asset
        entries[f"part:{asset}"] = {
            **entries.pop(f"source:{asset}"),
            "file": f"{DESK_LIBRARY}.glb",
            "focus": paths,
        }
        entries.pop(f"view:{asset}", None)
    entries[DESK_FILE_ID] = {
        **entries["part:desk-a"],
        "title": "桌柜 A–D",
        "members": [f"part:{asset}" for asset in DESK_IDS],
    }
    for entry in entries.values():
        if not entry.get("parts"):
            continue
        removed = [
            part
            for part in entry["parts"]
            if part["id"].removeprefix("source:") in DESK_IDS
        ]
        if not removed:
            continue
        paths = [path for path in views[entry["preview"]]["paths"] if desk_shape(path)]
        assert len(paths) == sum(part["count"] for part in removed)
        placements = defaultdict(lambda: defaultdict(int))
        for path in paths:
            extras = nodes[path]["extras"]
            resident = extras.get("resident", "").lower()
            assert resident in ("a", "b", "c", "d"), path
            placements[f"part:desk-{resident}"][extras["module"]] += 1
        replacement = []
        for key, counts in placements.items():
            # Count complete furniture instances only when all nine nodes are present.
            full = all(count == 9 for count in counts.values())
            replacement.append(
                {
                    "id": key,
                    "count": len(counts) if full else sum(counts.values()),
                    "unit": "实例" if full else "网格",
                }
            )
        entry["parts"] = [
            part for part in entry["parts"] if part not in removed
        ] + replacement


def build_menu(plan, inventory, source_categories, candidate, authoring):
    graph = build_relationships(plan, inventory)
    entries = graph["entries"]
    defaults = graph["defaults"]
    add_desks(entries, plan, inventory)
    entries.pop("view:pod-building")
    for part in entries["view:building-layout"]["parts"]:
        if part["id"] == "view:pod-building":
            part["id"] = "source:pod-building"

    original = {item["id"]: item for item in source_categories}
    furniture_groups = {
        group["id"]: group for group in original["furniture"]["children"]
    }
    furniture = []
    for group in furniture_groups.values():
        keys = []
        for item in group["children"]:
            asset = item["id"]
            if asset in DESK_IDS:
                if asset == "desk-a":
                    keys.append(DESK_FILE_ID)
                continue
            key = f"source:{asset}"
            if group["id"] in ("central", "terraces"):
                entries[key]["title"] += "专用部件"
            keys.append(key)
        label = {"central": "主楼专用部件", "terraces": "露台专用部件"}.get(
            group["id"], group["label"]
        )
        furniture.append(
            section(group["id"], label, [leaf(key, entries) for key in keys])
        )

    layouts = [
        leaf(f"view:{item['id']}", entries) for item in original["layouts"]["children"]
    ]
    layouts.append(
        section(
            "central-zones",
            "主楼分区",
            [
                leaf(f"view:{item['id']}", entries)
                for item in furniture_groups["central"]["children"]
            ],
        )
    )

    def scene_or_source(items):
        result = []
        for item in items:
            if "children" in item:
                result.append(
                    section(
                        item["id"], item["label"], scene_or_source(item["children"])
                    )
                )
                continue
            asset = item["id"]
            source = f"source:{asset}"
            key = source if asset.endswith("-library") else defaults[asset]
            result.append(leaf(key, entries))
            if key != source and source in entries:
                entries[source]["title"] += "几何"
                result.append(leaf(source, entries))
        return result

    buildings = scene_or_source(original["buildings"]["children"])
    courtyard = scene_or_source(original["courtyard"]["children"])
    entries["view:estate-layout"] = {
        "title": "全场景总组合",
        "file": "reassembled.scn",
        "kind": "assembly",
        "preview": "reassembled",
        "members": [
            "view:building-layout",
            "view:courtyard-layout",
            "view:bedroom-layout",
            "view:central-layout-1",
            "view:central-layout-2",
            "view:central-layout-3",
            *[f"view:terrace-layout-{index:02}" for index in range(1, 9)],
        ],
    }
    total = [
        leaf("view:estate-layout", entries),
        leaf("source:retained-placement-variants", entries),
    ]
    categories = [
        {**original[key], "children": children}
        for key, children in (
            ("furniture", furniture),
            ("layouts", layouts),
            ("buildings", buildings),
            ("courtyard", courtyard),
        )
    ]
    categories.append(
        {"id": "total", "label": "总组合", "color": "#675487", "children": total}
    )

    menu_ids = [
        item["id"]
        for category in categories
        for item in catalog_leaves(category["children"])
    ]
    member_libraries = {
        member: key
        for key in menu_ids
        if entries[key]["kind"] == "source"
        for member in entries[key].get("members", [])
    }
    keep = set(menu_ids) | member_libraries.keys()
    entries = {key: entry for key, entry in entries.items() if key in keep}
    add_reverse_links(entries, member_libraries)

    menu_files = [entries[key]["file"] for key in menu_ids]
    assert len(menu_ids) == len(set(menu_ids)) == len(set(menu_files))
    assert {name for name in menu_files if name.endswith(".glb")} == {
        path.name for path in authoring.glob("*.glb")
    }
    assert all(
        entries[item["id"]]["kind"] == "source" for item in catalog_leaves(furniture)
    )
    assert all(
        entries[item["id"]]["kind"] == "assembly" for item in catalog_leaves(layouts)
    )
    for key in menu_ids:
        entry = entries[key]
        file = entry["file"]
        directory = authoring if entry["kind"] == "source" else candidate / "models"
        if file == "reassembled.scn":
            directory = candidate
        assert (directory / file).is_file(), file
    return {"categories": categories, "entries": entries}
