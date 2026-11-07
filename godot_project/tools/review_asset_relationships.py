"""Build the Nest Lab file graph from the verified V044 assembly plan."""

from collections import Counter, defaultdict
from pathlib import PurePosixPath

CHAIR_LABELS = {
    "barrel_chair": "桶形单椅",
    "gaming_pouf": "圆柱软坐墩",
    "games_central_chair": "圆背木脚椅",
    "games_front_pouf": "花瓣软坐墩",
    "games_right_console_chair": "圆底游戏机椅",
    "lilac_game_armchair": "木座软包扶手椅",
    "quiet_central_reading_chair": "阅读扶手椅",
    "woven_floor_cushion": "编织圆地垫",
}
NATIVE_LABELS = {
    "Light3D": "光源",
    "WorldEnvironment": "环境",
    "CPUParticles3D": "粒子",
    "MultiMeshInstance3D": "实例批次",
    "MeshInstance3D": "原生网格",
}
GAME_PARTS = {
    "games_central_table": "桌子",
    "games_central_puzzle": "拼图",
    "games_central_rug": "地毯",
}


def placement_key(node):
    extras = node["extras"]
    return (
        extras.get("module"),
        extras.get("resident"),
        extras.get("designTemplateInstance", node["path"]),
    )


def build_relationships(plan, inventory):
    nodes = {node["path"]: node for node in inventory}
    mesh_at = plan["mesh_at_path"]
    owners = plan["geometry"]
    views = {view["id"]: view for view in plan["views"]}
    libraries = plan["authoring_libraries"]
    entries = {}
    defaults = {}
    chair_parts = {}
    chairs = []
    group_meshes = {
        PurePosixPath(path).name: shape
        for path, shape in mesh_at.items()
        if PurePosixPath(path).name.startswith("__ELFIE_INST_GROUP_")
    }

    for index, paths in enumerate(plan["showcase_groups"]["common-chairs"]):
        template = nodes[paths[0]]["extras"]["designTemplate"]
        name = template.removeprefix("part:shared_").rsplit("_", 1)[0]
        key = f"chair:{index}"
        entries[key] = {
            "title": CHAIR_LABELS.get(name, "座椅原型 " + str(index + 1)),
            "file": "common-chairs.glb",
            "kind": "source",
            "preview": "common-chairs",
            "focus": [f"Prototype_{index:03d}"],
        }
        chairs.append(key)
        for path in paths:
            shape = mesh_at[path]
            assert owners[shape]["asset"] == "common-chairs", path
            chair_parts[template, shape] = key

    for asset in libraries:
        view = views.get(asset)
        entry = {
            "title": view["menu"][-1] if view else "补充几何",
            "file": f"{asset}.glb",
            "kind": "source",
            "preview": asset if view else "reassembled",
        }
        if asset == "common-chairs":
            entry["members"] = chairs
        elif not view:
            entry["focus"] = [
                owner["source_path"]
                for owner in owners.values()
                if owner["asset"] == asset
            ]
        elif asset in plan["showcase_groups"]:
            matches = []
            count = 0
            for i, group in enumerate(plan["showcase_groups"][asset]):
                for j, path in enumerate(group):
                    count += 1
                    if owners[mesh_at[path]]["asset"] == asset:
                        matches.append(f"Prototype_{i:03d}/Part_{j:04d}")
            if len(matches) < count:
                entry["focus"] = matches
        elif asset != "pod-building":
            geometry_paths = [path for path in view["paths"] if path in mesh_at]
            owned_paths = [
                path
                for path in geometry_paths
                if owners[mesh_at[path]]["asset"] == asset
            ]
            if len(owned_paths) < len(view["paths"]):
                entry["focus"] = owned_paths
            if asset == "central-games-central":
                entry["detail"] = "、".join(
                    GAME_PARTS[name]
                    for name in GAME_PARTS
                    if any(PurePosixPath(path).name == name for path in owned_paths)
                )
        entries[f"source:{asset}"] = entry

    for asset, view in views.items():
        own_key = f"source:{asset}"
        units = defaultdict(set)
        batches = Counter()
        native = Counter()
        pod_paths = (
            {path for parts in plan["pod_parts"].values() for path in parts.values()}
            if asset == "building-layout"
            else set()
        )
        for path in view["paths"]:
            node = nodes[path]
            if path in pod_paths:
                continue
            if path in mesh_at:
                shape = mesh_at[path]
                owner = owners[shape]["asset"]
                chair = chair_parts.get((node["extras"].get("designTemplate"), shape))
                if chair is not None:
                    units[chair].add(placement_key(node))
                else:
                    units[f"source:{owner}"].add(path)
            elif (
                node["type"] == "MultiMeshInstance3D"
                and node["source_group"] in group_meshes
            ):
                shape = group_meshes[node["source_group"]]
                batches[f"source:{owners[shape]['asset']}"] += 1
            elif node["type"] in NATIVE_LABELS or node["type"].endswith("Light3D"):
                kind = "Light3D" if node["type"].endswith("Light3D") else node["type"]
                native[NATIVE_LABELS[kind]] += 1
        if pod_paths:
            units["view:pod-building"] = set(plan["pod_parts"])

        is_assembly = (
            view["category"] == "layouts"
            or asset.endswith(("-layout", "-planting"))
            or (asset.startswith("central-") and view["category"] == "furniture")
            or any(key != own_key and key not in chairs for key in units)
            or bool(batches or native)
            or (asset != "common-chairs" and any(key in chairs for key in units))
        )
        if own_key in entries and (
            not is_assembly or asset in ("pod-building", "common-chairs")
        ):
            defaults[asset] = own_key
            continue

        key = f"view:{asset}"
        defaults[asset] = key
        parts = []
        for target in units.keys() | batches.keys():
            item = {"id": target}
            if target.startswith(("chair:", "view:")):
                item["count"] = len(units[target])
                item["unit"] = "实例"
            elif target in batches and target in units:
                item["count"] = len(units[target])
                item["unit"] = "网格"
                item["batches"] = batches[target]
            elif target in batches:
                item["count"] = batches[target]
                item["unit"] = "批次"
            else:
                item["count"] = len(units[target])
                item["unit"] = "网格"
            parts.append(item)
        parts.sort(key=lambda item: (item["id"] != own_key, -item["count"], item["id"]))
        entries[key] = {
            "title": view["menu"][-1],
            "file": f"{asset}.scn",
            "kind": "assembly" if parts else "scene",
            "preview": asset,
            "parts": parts,
            "native": dict(native),
        }

    entries["view:pod-building"] = {
        "title": "共享小屋",
        "file": "pod-building.scn",
        "kind": "assembly",
        "preview": "pod-building",
        "parts": [{"id": "source:pod-building", "count": 1, "unit": "原型"}],
    }

    return {"defaults": defaults, "entries": entries}


def add_reverse_links(entries, member_libraries):
    for key, entry in entries.items():
        for part in entry.get("parts", []):
            reverse = {**part, "id": key}
            entries[part["id"]].setdefault("usedBy", []).append(reverse)
            if part["id"] in member_libraries:
                library = entries[member_libraries[part["id"]]]
                usages = library.setdefault("usedBy", [])
                existing = next((usage for usage in usages if usage["id"] == key), None)
                if existing is not None and existing["unit"] == reverse["unit"]:
                    existing["count"] += reverse["count"]
                elif existing is not None:
                    existing.update(count=0, unit="")
                else:
                    usages.append(reverse.copy())

    for entry in entries.values():
        if "usedBy" in entry:
            entry["usedBy"].sort(key=lambda edge: (-edge["count"], edge["id"]))
        if "focus" in entry:
            assert entry["focus"], entry["file"]
