"""Build the approved furniture directory from the frozen V044 placement data."""

import json
import mmap
import os
import shutil
import struct
import tempfile
from collections import defaultdict
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path

from audit_shared_geometry import AUTHORING, BUILD, ROOT, glb_meshes
from export_menu_assets import DESK_IDS, material_signature, prepare_menu_assets
from export_shared_asset_sources import CANDIDATE, Library, read_document
from furniture_components import (
    attached_fixture,
    component_for,
    component_rows,
    prototype_groups,
    reference_rows,
)
from furniture_geometry_reuse import reuse_courtyard_lamps, reuse_tabletop_geometry
from review_asset_menu import build_menu, catalog_leaves, leaf, section

DESTINATION = BUILD / "furniture-v044-organized"
GROUND_ASSEMBLY = "view:courtyard-ground"
GROUND_ASSEMBLY_FILE = "courtyard-ground.scn"
GROUND_SURFACES = (
    "shared-ground",
    "forest-ground",
    "meadow-ground",
    "forest-path",
    "meadow-plaza",
)
COURTYARD_COUNT = 17
COURTYARD_DEPENDENCIES = {
    "source:environment": "view:courtyard-layout",
    "view:tree-one": "view:forest-layout",
    "view:fountain": "view:waterside-layout",
    "view:waterfall": "view:waterside-layout",
    "source:waterside-path": "view:waterside-layout",
    "source:shore-stones": "view:waterside-layout",
}
# Each row is one plant from the frozen prototype families, before placement.
PLANT_PROTOTYPES = (
    (52,),
    (53,),
    (54,),
    (55,),
    (68,),
    (57, 58, 59, 60),
    (61, 62, 63),
    (64, 65, 66, 67),
)
DISPLAY_AREAS = {
    "central-games-bookshelf": ("games_left_curved_bookshelf", "弧形书架区"),
    "central-games-cabinet": ("games_rear_display", "陈列柜区"),
}
FLOORS = {
    1: ("central-living",),
    2: (
        "central-games-central",
        "central-games-chess",
        "central-games-console",
        "central-games-toys",
        *DISPLAY_AREAS,
    ),
    3: (
        "central-quiet-central",
        "central-quiet-sofa",
        "central-quiet-daybed",
        "central-quiet-rear",
        "central-quiet-desk",
    ),
}
FLOOR_LABELS = {1: "一楼", 2: "二楼", 3: "三楼"}
LOCATIONS = {
    "bedroom": "卧室",
    "terraces": "露台",
    **{f"main-{floor}": f"主楼{label}" for floor, label in FLOOR_LABELS.items()},
    "main-shared": "主楼共享",
}
STANDALONE = {"central-games-console", "central-games-toys", "central-games-cabinet"}
BEDROOM_SETS = tuple(f"bedroom-set-{slot}" for slot in "abcd")
TERRACES = tuple(f"terrace-layout-{index:02}" for index in range(1, 9))

# Library ownership and menu order follow the confirmed use locations.
SHARED = {
    "bedroom": {
        "bed-shared": "床与床品共用件",
        "bedroom-cabinet": "共用柜体",
        "chair": "花瓣转椅",
        "bedroom-lamps": "台灯",
        "bedroom-planters": "桌面盆栽",
        "bedroom-rug": "地垫",
    },
    "main": {
        "main-chairs": "座椅库",
        "main-tables": "桌几库",
        "main-planters": "植物库",
        "main-decor": "摆件库",
        "main-frames": "画框",
    },
    "terraces": {
        "terrace-chairs": "座椅库",
        "terrace-table": "矮桌",
        "terrace-planters": "盆栽库",
        "terrace-rug": "地毯",
        "terrace-fittings": "内衬与灯槽",
    },
}
SHARED_SOURCES = {
    "bedroom": {
        "bed": "bed-shared",
        "retained-placement-variants": "bed-shared",
        "desk-a": "bedroom-cabinet",
        "chair": "chair",
        "common-lamps": "bedroom-lamps",
        "common-plants": "bedroom-planters",
        "common-rugs": "bedroom-rug",
    },
    "main-floor-2": {"common-chairs": "main-chairs"},
    "main-floor-3": {"common-chairs": "main-chairs"},
    "main-cross-floor": {
        "common-tables": "main-tables",
        "common-plants": "main-planters",
        "common-frames": "main-frames",
    },
    "terraces": {
        "common-chairs": "terrace-chairs",
        "common-tables": "terrace-table",
        "common-plants": "terrace-planters",
        "common-rugs": "terrace-rug",
        "terrace-furniture-01": "terrace-fittings",
    },
}
SHARED_FILES = {
    asset: f"furniture/shared/{location}/{asset}.glb"
    for location, assets in SHARED.items()
    for asset in assets
}
SHARED_TITLES = {
    key: title for assets in SHARED.values() for key, title in assets.items()
}


def read_json(path):
    return json.loads(path.read_text())


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sorted_paths(paths):
    return sorted(paths, key=lambda path: (path.count("/"), path))


def layout_file(key):
    location = (
        "bedroom"
        if key.startswith("bedroom-")
        else "terraces"
        if key.startswith("terrace-")
        else "main"
    )
    return f"furniture/layouts/{location}/{key}.scn"


def set_file(key, extension):
    location = next(
        (
            f"main-floor-{floor}"
            for floor, ids in FLOORS.items()
            if key.removesuffix("-local") in ids
        ),
        "bedroom",
    )
    return f"furniture/sets/{location}/{key}.{extension}"


def desk_file(key, extension):
    return f"furniture/shared/bedroom/{key}.{extension}"


def landscape_sources(mesh_at, inventory):
    prototypes = {
        Path(path).name: path
        for path in mesh_at
        if Path(path).name.startswith("__ELFIE_INST_GROUP_")
    }
    sources = {
        node["path"]: prototypes[node["source_group"]]
        for node in inventory
        if node.get("source_group") in prototypes
    }
    # fountain_show.gd builds this batch from group 133 without tagging it.
    drops = "Generated/ObserverFountainLighting/RhythmicFountain/Nozzles/ReusedFountainDrops"
    sources[drops] = prototypes["__ELFIE_INST_GROUP_133"]
    return sources


def add_legacy_reference_paths(
    graph, views, owners, placement_meshes, plan, components
):
    entries = graph["entries"]
    pod_paths = {
        path for paths in plan["pod_parts"].values() for path in paths.values()
    }
    for category in graph["categories"]:
        if category["id"] != "buildings":
            continue
        for item in catalog_leaves(category["children"]):
            key = item["id"]
            if not key.startswith("view:") or key == "view:central-building":
                continue
            asset = key.removeprefix("view:")
            paths = views[asset]
            if asset == "building-layout":
                paths = paths - pod_paths
            parts, _ = reference_rows(
                sorted_paths(paths),
                [],
                {},
                owners,
                placement_meshes,
                entries,
                components,
            )
            if asset == "building-layout":
                parts.append(
                    {
                        "id": "source:pod-building",
                        "count": len(plan["pod_parts"]),
                        "unit": "实例",
                        "paths": sorted(plan["pod_parts"]),
                    }
                )
            entries[key]["parts"] = parts


def add_reverse_placements(entries):
    uses = defaultdict(lambda: defaultdict(list))
    for parent, entry in entries.items():
        for part in entry.get("parts", []):
            uses[part["id"]][parent].append(part)
    for key, consumers in uses.items():
        rows = []
        for parent, parts in consumers.items():
            # Several component rows can refer to the same source file.
            rows.append(
                {
                    "id": parent,
                    "count": parts[0]["count"] if len(parts) == 1 else 1,
                    "unit": parts[0]["unit"] if len(parts) == 1 else "文件",
                    "targetPaths": [
                        path for part in parts for path in part.get("paths", [])
                    ],
                }
            )
        entries[key]["usedBy"] = sorted(
            rows, key=lambda row: (-row["count"], row["id"])
        )


def geometry_partition(plan, nodes, views, decor_owners, beds):
    mesh_at = plan["mesh_at_path"]
    geometry = plan["geometry"]
    bed_shapes = {mesh_at[path] for path in beds}
    bedrooms = defaultdict(set)
    for path, node in nodes.items():
        extras = node["extras"]
        if extras.get("exportLayer") == "layout:pod":
            bedrooms[extras["module"], extras["resident"].lower()].add(path)
    assert len(bedrooms) == 32 and {len(paths) for paths in bedrooms.values()} == {211}

    contexts = {key: views[key] for key in TERRACES}
    for key in BEDROOM_SETS:
        contexts[key] = set().union(
            *(paths for (_, slot), paths in bedrooms.items() if slot == key[-1])
        )
    floor_at = {}
    for floor, sets in FLOORS.items():
        layout = f"central-layout-{floor}"
        children = set().union(*(views[key] for key in sets))
        assert children <= views[layout]
        contexts[layout] = views[layout] - children
        for key in (layout, *sets):
            floor_at[key] = floor
        contexts.update((key, views[key]) for key in sets)
    all_paths = set().union(*contexts.values())
    assert sum(map(len, contexts.values())) == len(all_paths)

    uses = defaultdict(set)
    for key, paths in contexts.items():
        for path in paths & mesh_at.keys():
            uses[mesh_at[path]].add(key)
    assert not any(
        shape in uses for path, shape in mesh_at.items() if path not in all_paths
    )

    owners = {}
    for shape, row in geometry.items():
        source = row["asset"]
        locations = uses[shape]
        if shape in decor_owners:
            owners[shape] = decor_owners[shape]
            continue
        if shape in bed_shapes:
            owners[shape] = SHARED_FILES["bed-shared"]
            continue
        if not locations:
            owners[shape] = f"{source}.glb"
            continue
        if len(locations) == 1:
            key = next(iter(locations))
            if source in DESK_IDS:
                owners[shape] = desk_file(f"desk-{key[-1]}-local", "glb")
            elif key in STANDALONE:
                owners[shape] = set_file(key, "glb")
            elif key.startswith("terrace-layout-") or key.startswith("central-layout-"):
                owners[shape] = layout_file(key).removesuffix(".scn") + "-local.glb"
            else:
                owners[shape] = set_file(key + "-local", "glb")
            continue
        if locations <= set(BEDROOM_SETS):
            location = "bedroom"
        elif locations <= set(TERRACES):
            location = "terraces"
        else:
            floors = {floor_at[key] for key in locations}
            location = (
                f"main-floor-{next(iter(floors))}"
                if len(floors) == 1
                else "main-cross-floor"
            )
        owners[shape] = SHARED_FILES[SHARED_SOURCES[location][source]]
    return owners, bedrooms


def courtyard_browse_menu():
    areas = [
        (
            "ground",
            "地面",
            (GROUND_ASSEMBLY, "地面与设施总装"),
            [
                ("source:shared-ground", "地形与铺装"),
                ("source:outdoor-lights", "路灯共享原型"),
            ],
        ),
        (
            "forest",
            "森林",
            ("view:forest-layout", "森林区总装"),
            [
                ("source:tree-one", "标志大树木结构"),
                ("source:forest-wood", "树干与树枝原型"),
                ("source:forest-foliage", "树叶与树冠原型"),
            ],
        ),
        (
            "waterside",
            "水榭",
            ("view:waterside-layout", "水榭区总装"),
            [
                ("source:lake", "湖面"),
                ("source:fountain", "喷泉与连接水道"),
                ("source:waterfall", "瀑布"),
                ("source:bench", "湖边长椅"),
            ],
        ),
        (
            "meadow",
            "草原",
            ("view:meadow-layout", "草原区总装"),
            [
                ("source:plant-library", "花草共享原型"),
                ("source:picnic", "野餐桌椅"),
                ("source:swing", "木质秋千"),
            ],
        ),
    ]

    def items(rows):
        return [{"id": key, "label": label} for key, label in rows]

    groups = [
        section(
            "courtyard-overview",
            "总览",
            [
                section(
                    "courtyard-all",
                    "全庭院",
                    items([("view:courtyard-layout", "庭院总装")]),
                ),
            ],
        ),
        section(
            "courtyard-areas",
            "功能区",
            [
                section(area, label, items([assembly]))
                for area, label, assembly, _ in areas
            ],
        ),
        section(
            "courtyard-parts",
            "详细部件",
            [section(area, label, items(parts)) for area, label, _, parts in areas],
        ),
    ]
    ids = [item["id"] for item in catalog_leaves(groups)]
    assert len(ids) == len(set(ids)) == COURTYARD_COUNT
    return groups


def courtyard_ground_paths(views, mesh_at, owners):
    lamp_paths = {
        path for path in views["outdoor-lights"] if "/OutdoorLighting/Fixture_" in path
    }
    # V044 has both generated roadside fixtures and the original entrance/ring lamps.
    authored_lamps = {
        path
        for path in views["courtyard-layout"] & mesh_at.keys()
        if owners[mesh_at[path]] == "outdoor-lights.glb"
        and "/OutdoorLighting/" not in path
    }
    lamp_paths.update(authored_lamps)
    lamp_paths.update(
        path
        for path in views["outdoor-lights"]
        if path.rpartition("/")[0] in authored_lamps
    )
    surfaces = set().union(*(views[key] for key in GROUND_SURFACES))
    surfaces.update(
        path
        for path in views["courtyard-layout"] & mesh_at.keys()
        if Path(path).name.startswith(
            (
                "CY R002 closed full island foundation",
                "CY R003 finish LANDSCAPE grouped stones",
                "CY R003 fountain connector ",
                "Preview 0_8m solid stone boundary",
                "Preview shallow limestone wall cap",
                "Lake inlay reference gold frame",
            )
        )
    )
    ground_shapes = {mesh_at[path] for path in surfaces if path in mesh_at}
    lamp_shapes = {mesh_at[path] for path in lamp_paths if path in mesh_at}
    assert not ground_shapes & lamp_shapes
    for path, shape in mesh_at.items():
        if shape in ground_shapes:
            assert path in surfaces, ("Ground mesh also placed outside ground", path)
    for shape in ground_shapes:
        owners[shape] = "shared-ground.glb"
    return surfaces, lamp_paths


def courtyard_component_paths(views, mesh_at, owners, ground_paths):
    """Use the evaluated V044 object families rather than the old preview labels."""
    meshes = views["courtyard-layout"] & mesh_at.keys()
    parts = {
        "lake": {
            path
            for path in meshes
            if owners[mesh_at[path]] == "lake.glb"
            or Path(path).name == "COMPLETE Inset natural lake"
        },
        "picnic": {
            path
            for path in meshes
            if Path(path).name.startswith(("Picnic ", "REPAIRED Picnic "))
        },
        "swing": {path for path in meshes if Path(path).name.startswith("Swing ")},
    }
    prototypes = {
        int(name.removeprefix("__ELFIE_INST_GROUP_")): path
        for path in mesh_at
        if (name := Path(path).name).startswith("__ELFIE_INST_GROUP_")
    }
    # These families are also defined by the frozen V044 source in estate_outdoor_access.gd.
    parts["plant-library"] = {
        prototypes[i] for i in (*range(32, 43), *range(52, 82), *range(88, 133))
    }
    parts["shore-stones"] = {prototypes[i] for i in range(82, 88)}
    parts["tree-one"] = {
        path for path in meshes if owners[mesh_at[path]] == "tree-one.glb"
    }
    parts["forest-wood"] = {prototypes[i] for i in (6, 18, 19, *range(23, 30), 43)} | {
        path
        for path in meshes & views["forest-layout"]
        if (name := Path(path).name).startswith(
            ("Boundary pruned wood ", "FOREST pruned low branches ")
        )
        or (name.startswith("MERGED_SEEDED_") and name.endswith("_wood"))
    }
    parts["forest-foliage"] = {
        prototypes[i]
        for i in (*range(6), *range(7, 16), 20, 21, 22, 30, 31, *range(44, 52))
    }
    waterfall = views["waterfall"] | {
        path
        for path in views["fountain"]
        if Path(path).name.startswith(
            (
                "CY R001 spillway outlet crest",
                "CY R001 spillway supporting outlet face",
                "CY R001 spillway receiving solid floor",
                "COMPLETE Inset natural lake receiving under spillway",
            )
        )
    }
    fountain = views["fountain"] - ground_paths - waterfall
    parts["fountain"] = (fountain & meshes) | {prototypes[133]}
    parts["waterfall"] = waterfall & meshes
    shapes = {key: {mesh_at[path] for path in paths} for key, paths in parts.items()}
    assert sum(map(len, shapes.values())) == len(set().union(*shapes.values()))
    for component, paths in parts.items():
        assert paths, component
        for path in paths:
            owners[mesh_at[path]] = f"{component}.glb"
    assert len(parts["lake"]) == 3 and len(parts["swing"]) == 8
    assert "forest-library.glb" not in owners.values()
    plant_groups = [
        [prototypes[index] for index in group] for group in PLANT_PROTOTYPES
    ]
    assert {mesh_at[path] for group in plant_groups for path in group} == shapes[
        "plant-library"
    ]
    return parts, plant_groups, fountain, waterfall


def courtyard_lamp_groups(paths, mesh_at, nodes):
    fixtures = defaultdict(list)
    for path in sorted_paths(paths & mesh_at.keys()):
        if "/OutdoorLighting/Fixture_" in path:
            fixture = path.split("/OutdoorLighting/", 1)[1].split("/", 1)[0]
        else:
            fixture = nodes[path]["extras"]["outdoor_fixture_id"]
        fixtures[fixture].append(path)
    prototypes = {}
    for paths in fixtures.values():
        shapes = tuple(sorted(mesh_at[path] for path in paths))
        prototypes.setdefault(shapes, paths)
    return list(prototypes.values())


def create_furniture_menu(plan, inventory, catalog, stage):
    nodes = {node["path"]: node for node in inventory}
    view_data = {view["id"]: view for view in plan["views"]}
    views = {key: set(view["paths"]) for key, view in view_data.items()}
    menu_authoring = prepare_menu_assets(CANDIDATE, plan)
    aliases = reuse_tabletop_geometry(plan, nodes)
    aliases.update(reuse_courtyard_lamps(plan))
    mesh_at = plan["mesh_at_path"]
    geometry = plan["geometry"]
    main_paths = set().union(
        views["central-building"],
        *(views[f"central-layout-{floor}"] for floor in FLOORS),
    )
    decor_owners = {}
    components = {}
    for path, node in nodes.items():
        library, part = component_for(path, node["extras"])
        if part:
            components[path] = part
        if library and path in main_paths and path in mesh_at:
            file = SHARED_FILES[
                "main-planters" if library == "plants" else "main-decor"
            ]
            assert decor_owners.setdefault(mesh_at[path], file) == file
    for key, (component, _) in DISPLAY_AREAS.items():
        # The stair-niche decor belongs to the floor layout beside these areas.
        views[key] = {
            path
            for path in views["central-games-display"]
            if path in components and components[path].key == component
        }
        assert views[key], key
    for floor, sets in FLOORS.items():
        for path in views[f"central-layout-{floor}"]:
            fixture = attached_fixture(path)
            if fixture and fixture[0] in sets:
                views[fixture[0]].add(path)
    beds = sorted_paths(
        path
        for path in mesh_at
        if path in components and components[path].key == "pod_bed"
    )
    owners, bedrooms = geometry_partition(plan, nodes, views, decor_owners, beds)
    ground_surfaces, lamp_paths = courtyard_ground_paths(views, mesh_at, owners)
    ground_paths = ground_surfaces | lamp_paths
    courtyard_parts, plant_groups, fountain, waterfall = courtyard_component_paths(
        views, mesh_at, owners, ground_paths
    )
    placement_meshes = {
        **mesh_at,
        **{
            path: mesh_at[source]
            for path, source in landscape_sources(mesh_at, inventory).items()
        },
    }
    file_shapes = defaultdict(list)
    for shape, file in owners.items():
        file_shapes[file].append(shape)
    all_shapes_by_source = defaultdict(set)
    for shape, row in geometry.items():
        all_shapes_by_source[row["asset"]].add(shape)

    graph = build_menu(
        plan,
        inventory,
        catalog["categories"],
        CANDIDATE,
        menu_authoring,
    )
    entries = graph["entries"]
    scenes = {}
    glb_nodes = {}

    def title_for(key):
        if key in DISPLAY_AREAS:
            return DISPLAY_AREAS[key][1]
        return view_data[key]["menu"][-1]

    def set_title(key, floor):
        return title_for(key).removeprefix(FLOOR_LABELS[floor])

    def source(file, title, paths, groups=None):
        key = f"source:{Path(file).stem}"
        assert file in file_shapes and key not in scenes, file
        paths = [
            path for path in paths if path in mesh_at and owners[mesh_at[path]] == file
        ]
        groups = [[p for p in group if p in paths] for group in (groups or [])]
        groups = [group for group in groups if group]
        seen = {mesh_at[path] for path in paths}
        glb_nodes[file] = paths + [
            geometry[shape]["source_path"]
            for shape in sorted(file_shapes[file])
            if shape not in seen
        ]
        entries[key] = {"title": title, "file": file, "kind": "source", "preview": key}
        rows = component_rows(paths, components, mesh_at)
        if rows:
            entries[key]["components"] = rows
        scenes[key] = {
            "file": f"previews/{Path(file).stem}.scn",
            "paths": paths or glb_nodes[file],
            "children": [],
            "groups": groups,
        }
        if groups and Path(file).stem in SHARED["main"]:
            scenes[key]["front_row"] = True
        return key

    def scene(key, file, title, paths, children=(), *, landscape=False):
        children = list(children)
        direct = set(paths)
        for child in children:
            assert coverage[child] <= direct, (key, child)
            direct -= coverage[child]
        direct = sorted_paths(direct)
        parts, bindings = reference_rows(
            direct,
            children,
            coverage,
            owners,
            placement_meshes if landscape else mesh_at,
            entries,
            components,
        )
        entries[key] = {
            "title": title,
            "file": file,
            "kind": "assembly",
            "preview": key,
            "parts": parts,
        }
        scenes[key] = {
            "file": file,
            "paths": direct,
            "children": children,
            "groups": [],
            "bindings": bindings,
        }
        coverage[key] = set(paths)
        return key

    coverage = {}
    for key in sorted(STANDALONE):
        floor = next(floor for floor, keys in FLOORS.items() if key in keys)
        asset = source(
            set_file(key, "glb"), set_title(key, floor), sorted_paths(views[key])
        )
        assert set(scenes[asset]["paths"]) == views[key]
        coverage[asset] = views[key]

    for file, shapes in file_shapes.items():
        if not file.startswith("furniture/") or file in glb_nodes:
            continue
        name = Path(file).stem
        if name in ("main-chairs", "main-planters", "main-decor"):
            paths = sorted_paths(
                path for path in main_paths if owners.get(mesh_at.get(path)) == file
            )
            groups = prototype_groups(paths, components, mesh_at)
            source(
                file,
                SHARED_TITLES[name],
                [p for group in groups for p in group],
                groups,
            )
        elif name in SHARED_TITLES:
            group_source = geometry[shapes[0]]["asset"]
            groups = plan["showcase_groups"].get(group_source, [])
            preferred = [p for group in groups for p in group]
            if not preferred:
                preview = {
                    "bed-shared": "bed",
                    "bedroom-cabinet": "desk-a",
                    "terrace-fittings": "terrace-layout-01",
                }.get(name, group_source)
                preferred = sorted_paths(views[preview])
            source(file, SHARED_TITLES[name], preferred, groups)
        else:
            base = name.removesuffix("-local")
            title = title_for(base)
            source(
                file,
                title.removesuffix("区")
                if base in DISPLAY_AREAS
                else title + "专用部件",
                sorted_paths(views[base]),
            )
    assert set(scenes["source:bed-shared"]["paths"]) == views["bed"], (
        "Incomplete reference bed"
    )
    glb_nodes[SHARED_FILES["bed-shared"]] = beds

    for key in DESK_IDS:
        paths = {
            p
            for p in views[key]
            if mesh_at.get(p) in geometry and geometry[mesh_at[p]]["asset"] in DESK_IDS
        }
        assert len(paths) == 9
        scene(f"view:{key}", desk_file(key, "scn"), f"桌柜 {key[-1].upper()}", paths)
    for key in BEDROOM_SETS:
        scene(
            f"view:{key}",
            set_file(key, "scn"),
            f"套装 {key[-1].upper()}",
            views[key],
        )
    scene(
        "view:bedroom-layout",
        layout_file("bedroom-layout"),
        "卧室完整布置",
        views["bedroom-layout"],
        [f"view:{key}" for key in BEDROOM_SETS],
    )
    bedrooms_by_room = ["view:bedroom-layout"]
    for module in sorted({module for module, _ in bedrooms} - {"M01"}):
        paths = set().union(*(bedrooms[module, slot] for slot in "abcd"))
        bedrooms_by_room.append(
            scene(
                f"placement:bedroom-{module.lower()}",
                f"furniture/layouts/bedroom/placements/{module.lower()}.scn",
                f"{module} 卧室摆位",
                paths,
            )
        )
    entries["view:bedroom-layout"]["members"] = bedrooms_by_room[1:]
    for floor, sets in FLOORS.items():
        layout = f"central-layout-{floor}"
        children = []
        for key in sets:
            if key in STANDALONE:
                children.append(f"source:{key}")
            else:
                children.append(
                    scene(
                        f"view:{key}",
                        set_file(key, "scn"),
                        set_title(key, floor),
                        views[key],
                    )
                )
        scene(
            f"view:{layout}",
            layout_file(layout),
            title_for(layout).removeprefix("主楼"),
            views[layout],
            children,
        )
    for key in TERRACES:
        assert views[key] == views[key.replace("layout", "furniture")]
        title = title_for(key).removesuffix("布置")
        scene(f"view:{key}", layout_file(key), title[:3] + " " + title[3:], views[key])
    scene(
        "view:central-building",
        "central-building.scn",
        "主楼",
        views["central-building"],
    )

    def leaves(keys):
        return [leaf(key, entries) for key in keys]

    def furniture_section(group, label, placements):
        return section(
            group,
            label,
            [
                section(location, name, leaves(placements[location]))
                for location, name in LOCATIONS.items()
                if location in placements
            ],
        )

    furniture_parts = {
        "bedroom": [
            *(f"source:{key}" for key in SHARED["bedroom"]),
            *(f"source:{key}-local" for key in DESK_IDS),
        ],
        "terraces": [
            *(f"source:{key}" for key in SHARED["terraces"]),
            *(f"source:{key}-local" for key in TERRACES),
        ],
        **{
            f"main-{floor}": [
                f"source:{key}-local" for key in keys if key not in STANDALONE
            ]
            for floor, keys in FLOORS.items()
        },
        "main-shared": [f"source:{key}" for key in SHARED["main"]],
    }
    furniture = [
        furniture_section(
            "furniture-layouts",
            "完整布置",
            {
                "bedroom": bedrooms_by_room,
                "terraces": [f"view:{key}" for key in TERRACES],
                **{
                    f"main-{floor}": [f"view:central-layout-{floor}"]
                    for floor in FLOORS
                },
            },
        ),
        furniture_section(
            "furniture-sets",
            "家具套装",
            {
                "bedroom": [f"view:{key}" for key in (*BEDROOM_SETS, *DESK_IDS)],
                **{
                    f"main-{floor}": [
                        f"{'source' if key in STANDALONE else 'view'}:{key}"
                        for key in keys
                    ]
                    for floor, keys in FLOORS.items()
                },
            },
        ),
        furniture_section("furniture-shared", "家具与装饰", furniture_parts),
    ]
    original = {category["id"]: category for category in graph["categories"]}
    categories = [
        {**original["furniture"], "children": furniture},
        original["buildings"],
        original["courtyard"],
        {
            **original["total"],
            "label": "总组装",
            "children": leaves(
                ["view:estate-layout", "source:retained-placement-variants"]
            ),
        },
    ]

    entries["source:central-building"]["focus"] = [
        path
        for path in sorted_paths(views["central-building"])
        if owners.get(mesh_at.get(path)) == "central-building.glb"
    ]
    entries["source:retained-placement-variants"]["focus"] = [
        geometry[shape]["source_path"]
        for shape in file_shapes["retained-placement-variants.glb"]
    ]
    source("shared-ground.glb", "地形与铺装", sorted_paths(ground_surfaces))
    lamp_groups = courtyard_lamp_groups(lamp_paths, mesh_at, nodes)
    source(
        "outdoor-lights.glb",
        "路灯共享原型",
        [path for group in lamp_groups for path in group],
        lamp_groups,
    )
    scenes["source:outdoor-lights"]["front_row"] = True
    for key, title in (
        ("lake", "湖面"),
        ("picnic", "野餐桌椅"),
        ("swing", "木质秋千"),
        ("tree-one", "标志大树木结构"),
        ("fountain", "喷泉与连接水道"),
        ("waterfall", "瀑布"),
    ):
        source(f"{key}.glb", title, sorted_paths(courtyard_parts[key]))
    stones = sorted_paths(courtyard_parts["shore-stones"])
    source("shore-stones.glb", "岸石共享几何", stones, [[path] for path in stones])
    source(
        "plant-library.glb",
        "花草共享原型",
        [path for group in plant_groups for path in group],
        plant_groups,
    )
    for key, title in (
        ("forest-wood", "树干与树枝原型"),
        ("forest-foliage", "树叶与树冠原型"),
    ):
        prototypes = {
            mesh_at[path]: path for path in sorted_paths(courtyard_parts[key])
        }
        paths = list(prototypes.values())
        source(f"{key}.glb", title, paths, [[path] for path in paths])
    for key, title in (
        ("source:environment", "昼夜环境几何"),
        ("source:waterside-path", "湖畔平台基础"),
    ):
        entries[key]["title"] = title

    add_legacy_reference_paths(graph, views, owners, placement_meshes, plan, components)
    building_roots = [
        "view:central-building",
        "view:bedroom-layout",
        *(f"view:{key}" for key in TERRACES),
        *(f"view:central-layout-{floor}" for floor in FLOORS),
        *(key for key in coverage if key.startswith("placement:")),
    ]
    building_placements = set().union(*(coverage[key] for key in building_roots))
    assert len(building_placements) == 7188 + len(views["central-building"])
    courtyard_paths = views["courtyard-layout"] - building_placements
    scene(GROUND_ASSEMBLY, GROUND_ASSEMBLY_FILE, "地面与设施总装", ground_paths)
    scene("view:fountain", "fountain.scn", "喷泉与连接水道", fountain, landscape=True)
    scene("view:waterfall", "waterfall.scn", "瀑布", waterfall, landscape=True)
    water_features = fountain | waterfall
    shared_paths = ground_paths | views["environment"]
    # The primary tree canopy was exported as V044 batches, not as part of the trunk GLB.
    canopy_groups = {f"__ELFIE_INST_GROUP_{i:03d}" for i in range(6, 16)}
    canopy = {
        path
        for path in views["courtyard-layout"]
        if nodes[path].get("source_group") in canopy_groups
    }
    tree = views["tree-one"] | canopy
    scene("view:tree-one", "landmark-tree.scn", "标志大树", tree, landscape=True)
    zones = (
        (
            "forest-layout",
            "森林区总装",
            (views["forest-layout"] | tree) - shared_paths - water_features,
            ("view:tree-one",),
        ),
        (
            "waterside-layout",
            "水榭区总装",
            (views["waterside-layout"] | water_features) - shared_paths - tree,
            ("view:fountain", "view:waterfall"),
        ),
        (
            "meadow-layout",
            "草原区总装",
            views["meadow-layout"] - shared_paths - water_features - tree,
            (),
        ),
    )
    for key, title, paths, children in zones:
        scene(
            f"view:{key}",
            f"{key}.scn",
            title,
            paths & courtyard_paths,
            children,
            landscape=True,
        )
    courtyard_children = [GROUND_ASSEMBLY, *(f"view:{key}" for key, *_ in zones)]
    assert sum(len(coverage[key]) for key in courtyard_children) == len(
        set().union(*(coverage[key] for key in courtyard_children))
    ), "Courtyard placements assigned to more than one area"
    scene(
        "view:courtyard-layout",
        "courtyard-layout.scn",
        "庭院总装",
        courtyard_paths,
        courtyard_children,
        landscape=True,
    )

    courtyard = next(row for row in categories if row["id"] == "courtyard")
    courtyard["children"] = courtyard_browse_menu()
    courtyard_files = {}
    for group in courtyard["children"]:
        for area in group["children"]:
            for item in area["children"]:
                key = item["id"]
                section_name = group["id"].removeprefix("courtyard-")
                courtyard_files[key] = Path("courtyard") / section_name / area["id"]
    for key, owner in COURTYARD_DEPENDENCIES.items():
        assert key in {part["id"] for part in entries[owner]["parts"]}, (key, owner)
        entries[key]["owner"] = owner
        courtyard_files[key] = (
            courtyard_files[owner] / Path(entries[owner]["file"]).stem
        )
    for key, directory in courtyard_files.items():
        old = entries[key]["file"]
        new = (directory / Path(old).name).as_posix()
        entries[key]["file"] = new
        if key in scenes and entries[key]["kind"] == "assembly":
            scenes[key]["file"] = new
        if old in file_shapes:
            shapes = file_shapes.pop(old)
            file_shapes[new] = shapes
            for shape in shapes:
                owners[shape] = new
            if old in glb_nodes:
                glb_nodes[new] = glb_nodes.pop(old)

    menu_ids = [
        item["id"]
        for category in categories
        for item in catalog_leaves(category["children"])
    ]
    menu_ids.extend(COURTYARD_DEPENDENCIES)
    assert len(menu_ids) == len(set(menu_ids)), "Duplicate asset entry"
    used = {key: entries[key] for key in menu_ids}
    for key, row in used.items():
        row.pop("usedBy", None)
        references = set(row.get("members", ())) | {
            part["id"] for part in row.get("parts", ())
        }
        assert references <= used.keys(), (
            key,
            "references outside menu",
            sorted(references - used.keys()),
        )
    add_reverse_placements(used)
    audit_furniture_components(used, scenes, coverage, mesh_at, components)
    files = [used[key]["file"] for key in menu_ids]
    assert len(files) == len(set(files)), "Menu leaves must map to distinct files"
    assert {file for file in files if file.endswith(".glb")} == file_shapes.keys()
    previews = {}
    for key, row in used.items():
        if key in scenes:
            scene_file = scenes[key]["file"]
            path = (
                scene_file
                if scene_file.startswith("previews/")
                else f"assets/{scene_file}"
            )
        else:
            scene_file = row["preview"]
            path = (
                "reassembled.scn"
                if scene_file == "reassembled"
                else f"models/{scene_file}.scn"
            )
        previews[key] = {
            "path": path,
            "base": row["preview"].removeprefix("view:")
            if key in courtyard_files
            else row["preview"],
            "focus": row.get("focus", []),
            "furniture": row["file"].startswith("furniture/"),
        }
        if key != "view:estate-layout":
            row["preview"] = key

    assembly_roots = [*building_roots, "view:courtyard-layout"]
    assembled = building_placements | courtyard_paths
    assert sum(len(coverage[key]) for key in assembly_roots) == len(assembled)
    write_json(stage / "file-graph.json", {"categories": categories, "entries": used})
    write_json(stage / "menu.json", menu_ids)
    write_json(stage / "asset-previews.json", previews)
    write_json(
        stage / "native-plan.json",
        {
            "scenes": scenes,
            "assembly_roots": assembly_roots,
            "placements": len(assembled),
            "courtyard_placements": len(courtyard_paths),
            "geometry_aliases": aliases,
        },
    )
    write_json(
        stage / "geometry-owners.json",
        {
            **owners,
            **{key: owners[record["geometry"]] for key, record in aliases.items()},
        },
    )
    return file_shapes, all_shapes_by_source, glb_nodes, components


def audit_furniture_components(entries, scenes, coverage, mesh_at, components):
    for key, entry in entries.items():
        if not entry["file"].startswith("furniture/"):
            continue
        source = entry["kind"] == "source"
        wanted = set(scenes[key]["paths"]) if source else coverage[key]
        rows = entry.get("components" if source else "parts", ())
        paths = [path for row in rows for path in row.get("paths", ())]
        assert len(paths) == len(set(paths)), (key, "overlapping furniture components")
        missing = {
            path for path in wanted if path in mesh_at or path in components
        } - set(paths)
        assert not missing, (key, "unassigned furniture geometry", sorted(missing)[:8])
        assert set(paths) <= wanted, (key, "foreign furniture components")
        component_owners = {}
        for row in rows:
            if source:
                assert set(row.get("prototypePaths", row["paths"])) <= set(row["paths"])
            elif (
                row["id"].startswith("source:")
                and row["id"] not in scenes[key]["children"]
            ):
                assert row.get("component"), (
                    key,
                    "unnamed furniture component",
                    row["id"],
                )
                assert set(row["targetPaths"]) <= set(scenes[row["id"]]["paths"]), (
                    key,
                    row["id"],
                )
                for path in row["paths"]:
                    part = components[path]
                    assert component_owners.setdefault(part, row["id"]) == row["id"], (
                        key,
                        part,
                        "split furniture",
                    )


def export_geometry(
    plan, stage, file_shapes, all_shapes_by_source, glb_nodes, components
):
    assets = stage / "assets"
    textures = assets / "textures"
    shutil.copytree(CANDIDATE / "authoring/textures", textures)
    geometry = plan["geometry"]
    mesh_at = plan["mesh_at_path"]
    rebuilt = {
        file: set(shapes)
        for file, shapes in file_shapes.items()
        if set(shapes) != all_shapes_by_source.get(Path(file).stem)
        or file.startswith("furniture/")
    }
    material_at = {}
    with ExitStack() as stack:
        documents = {}
        placements = {}
        required_paths = {
            path
            for file, shapes in rebuilt.items()
            for path in glb_nodes.get(
                file, [geometry[shape]["source_path"] for shape in shapes]
            )
        }
        for source in sorted(AUTHORING.glob("*.glb")):
            stream = stack.enter_context(source.open("rb"))
            binary = stack.enter_context(
                mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ)
            )
            document, start = read_document(binary)
            documents[source.stem] = (document, binary, start)
            for node in document["nodes"]:
                path = node.get("extras", {}).get("v044_path")
                if path in required_paths and "mesh" in node:
                    placements.setdefault(path, (source.stem, node))
        for file, shapes in sorted(file_shapes.items()):
            output = assets / file
            output.parent.mkdir(parents=True, exist_ok=True)
            if file not in rebuilt:
                source = CANDIDATE / "authoring" / output.name
                if file.startswith("courtyard/"):
                    copy_courtyard_glb(source, output, textures)
                else:
                    shutil.copyfile(source, output)
                continue
            paths = glb_nodes.get(file) or [
                geometry[shape]["source_path"] for shape in shapes
            ]
            material_at[file] = export_library(
                output,
                textures,
                paths,
                mesh_at,
                geometry,
                placements,
                documents,
                components,
            )

    found = {}
    buffers = defaultdict(set)
    material_variants = 0
    for file in file_shapes:
        output = assets / file
        records = glb_meshes(output, buffers)
        with (
            output.open("rb") as stream,
            mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as binary,
        ):
            document, start = read_document(binary)
            accessor_bindings = {}
            for record in records:
                shape = record["shape"]
                binding = [
                    {
                        key: value
                        for key, value in primitive.items()
                        if key != "material"
                    }
                    for primitive in document["meshes"][record["mesh"]]["primitives"]
                ]
                if shape in found:
                    # Material variants reuse the same mesh accessors in the same GLB.
                    assert found[shape] == (file, record["payload"]), (file, shape)
                    assert accessor_bindings[shape] == binding, (file, shape)
                    material_variants += 1
                else:
                    found[shape] = (file, record["payload"])
                    accessor_bindings[shape] = binding
            for image in document.get("images", ()):
                texture = output.parent / image["uri"]
                assert (
                    texture.resolve().parent == textures.resolve() and texture.is_file()
                ), (file, texture)
            if file in material_at:
                library = Library(document, binary, start, textures)
                actual = {
                    node["extras"]["v044_path"]: material_signature(
                        document, library, document["meshes"][node["mesh"]]
                    )
                    for node in document["nodes"]
                    if "mesh" in node
                }
                assert actual == material_at[file], (file, "placement materials")
    assert found == {
        shape: (file, geometry[shape]["payload"])
        for file, shapes in file_shapes.items()
        for shape in shapes
    }
    print(
        f"FURNITURE_GEOMETRY_PASS glbs={len(file_shapes)} unique_shapes={len(found)} "
        f"shared_geometry_material_variants={material_variants}"
    )


def copy_courtyard_glb(source, output, textures):
    """Relocate texture URIs while preserving the scene and binary mesh buffers."""
    with (
        source.open("rb") as stream,
        mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as binary,
    ):
        document, start = read_document(binary)
        for image in document.get("images", ()):
            texture = textures / Path(image["uri"]).name
            image["uri"] = Path(os.path.relpath(texture, output.parent)).as_posix()
        data = json.dumps(document, separators=(",", ":")).encode()
        data += b" " * (-len(data) % 4)
        binary.seek(start - 8)
        with output.open("wb") as target:
            length = 20 + len(data) + len(binary) - binary.tell()
            target.write(
                struct.pack("<4sIIII", b"glTF", 2, length, len(data), 0x4E4F534A)
            )
            target.write(data)
            shutil.copyfileobj(binary, target)


def export_library(
    output, textures, paths, mesh_at, geometry, placements, documents, components
):
    source_names = {geometry[mesh_at[path]]["asset"] for path in paths}
    source_names.update(placements[path][0] for path in paths)
    texture_uri = Path(os.path.relpath(textures, output.parent)).as_posix()
    libraries = {
        name: Library(*documents[name], textures, texture_uri)
        for name in sorted(source_names)
    }
    combined = next(iter(libraries.values()))
    for library in libraries.values():
        for key in ("extensionsUsed", "extensionsRequired"):
            if key in library.output:
                combined.output[key] = sorted(
                    set(combined.output.get(key, ())) | set(library.output[key])
                )
        library.output = combined.output
        library.buffers = combined.buffers
        library.payload_views = combined.payload_views

    variants = defaultdict(dict)
    material_at = {}
    nodes = []
    roots = []
    furniture_groups = defaultdict(list)
    for path in paths:
        shape = mesh_at[path]
        info = geometry[shape]
        origin, placement = placements[path]
        source = libraries[origin]
        source_mesh = source.source["meshes"][placement["mesh"]]
        material = material_signature(source.source, source, source_mesh)
        material_at[path] = material
        signature = json.dumps(material, sort_keys=True)
        mesh_variants = variants[shape]
        if signature not in mesh_variants:
            mesh_index = libraries[info["asset"]].mesh(info["original_mesh"], shape)
            meshes = combined.output["meshes"]
            mesh = meshes[mesh_index]
            if mesh_variants:
                mesh = deepcopy(mesh)
                mesh["name"] += f"_material_{len(mesh_variants)}"
                mesh_index = len(meshes)
                meshes.append(mesh)
            assert len(mesh["primitives"]) == len(source_mesh["primitives"])
            for target, original in zip(mesh["primitives"], source_mesh["primitives"]):
                if "material" in original:
                    target["material"] = source.material(original["material"])
                else:
                    target.pop("material", None)
            mesh_variants[signature] = mesh_index
        extras = {**placement["extras"], "geometry_id": shape}
        if path in components:
            part = components[path]
            extras.update(component_id=part.key, component_name=part.title)
            furniture_groups[part].append(len(nodes) + 1)
        else:
            roots.append(len(nodes) + 1)
        nodes.append(
            {
                **placement,
                "name": f"part_{len(nodes):05}",
                "mesh": mesh_variants[signature],
                "extras": extras,
            }
        )
    variants = []
    for part, children in furniture_groups.items():
        index = len(nodes) + 1
        nodes.append(
            {
                "name": part.title,
                "children": children,
                "extras": {"component_id": part.key},
            }
        )
        if output.stem == "bed-shared" and part.placement != "M01-A":
            variants.append({"name": part.placement, "nodes": [index]})
        else:
            roots.append(index)
    if output.stem == "bed-shared":
        assert len(roots) == 1 and len(variants) == 31
        assert {len(children) for children in furniture_groups.values()} == {132}
    combined.save(output, nodes, roots, variants)
    return material_at


def write_authoring_bindings(stage, mesh_at, inventory):
    """Resolve each mesh or instance batch to a named node in its owning GLB."""
    graph = read_json(stage / "file-graph.json")["entries"]
    scenes = read_json(stage / "native-plan.json")["scenes"]
    assets = stage / "assets"
    source_paths = landscape_sources(mesh_at, inventory)
    bindings = {}
    for key, record in scenes.items():
        if not record["file"].startswith(("furniture/", "courtyard/")):
            continue
        bindings[key] = dict(record["bindings"])
        for child in record["children"]:
            if graph[child]["kind"] == "source":
                bindings[key][child] = scenes[child]["paths"]
    batches = {row["path"] for row in inventory if row["type"] == "MultiMeshInstance3D"}
    for key, scene in bindings.items():
        if scenes[key]["file"].startswith("courtyard/"):
            used = {path for paths in scene.values() for path in paths}
            assert (
                batches.intersection(scenes[key]["paths"]) <= used & source_paths.keys()
            ), key
    needed = {
        source_paths.get(path, path)
        for scene in bindings.values()
        for paths in scene.values()
        for path in paths
        if path in mesh_at or path in source_paths
    }

    def mesh_nodes(path):
        with (
            path.open("rb") as stream,
            mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data,
        ):
            document, start = read_document(data)
            library = Library(document, data, start, assets / "textures")
            signatures = {}
            for node in document["nodes"]:
                if "mesh" not in node:
                    continue
                index = node["mesh"]
                if index not in signatures:
                    signatures[index] = json.dumps(
                        material_signature(
                            document, library, document["meshes"][index]
                        ),
                        sort_keys=True,
                    )
                yield node, signatures[index]

    materials = {}
    for file in sorted(AUTHORING.glob("*.glb")):
        for node, material in mesh_nodes(file):
            path = node["extras"]["v044_path"]
            if path in needed:
                materials.setdefault(path, material)
    assert needed == materials.keys(), "Missing furniture placement materials"

    libraries = {}
    for asset in {asset for scene in bindings.values() for asset in scene}:
        by_shape = {}
        by_material = {}
        for node, material in mesh_nodes(assets / graph[asset]["file"]):
            shape = node["extras"]["geometry_id"]
            by_shape.setdefault(shape, node["name"])
            by_material.setdefault((shape, material), node["name"])
        libraries[asset] = by_shape, by_material

    result = {}
    for key, scene in bindings.items():
        result[key] = {}
        for asset, paths in scene.items():
            by_shape, by_material = libraries[asset]
            result[key][asset] = {}
            for path in paths:
                source = source_paths.get(path, path)
                if source not in mesh_at:
                    continue  # The assembly retains the native light or fixture.
                shape = mesh_at[source]
                match = by_material.get((shape, materials[source]))
                result[key][asset][path] = {
                    "node": match or by_shape[shape],
                    "preserve_material": match is None,
                }
    write_json(stage / "authoring-bindings.json", result)


def main():
    if DESTINATION.exists():
        raise FileExistsError(
            f"Preserve the current furniture candidate before rebuilding: {DESTINATION}"
        )
    plan = read_json(CANDIDATE / "assembly-plan.json")
    inventory = read_json(BUILD / "full-inventory/static-nodes.json")
    catalog = read_json(ROOT / "godot_project/nest/asset_catalog.json")
    assert plan["snapshot_sha256"] == catalog["snapshot_sha256"]
    stage = Path(tempfile.mkdtemp(prefix="furniture-v044-", dir=BUILD))
    try:
        files, old_sources, placements, components = create_furniture_menu(
            plan, inventory, catalog, stage
        )
        export_geometry(plan, stage, files, old_sources, placements, components)
        write_authoring_bindings(stage, plan["mesh_at_path"], inventory)
        stage.rename(DESTINATION)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__ == "__main__":
    main()
