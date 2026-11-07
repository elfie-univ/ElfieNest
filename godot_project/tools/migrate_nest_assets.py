"""Seed the formal split estate from the audited V044 extraction once."""

import json
import mmap
import os
import shutil
import struct
from collections import defaultdict
from pathlib import Path

from audit_shared_geometry import BUILD, NEST, glb_meshes
from export_shared_asset_sources import CANDIDATE, Library, read_document
from organize_furniture_assets import DESTINATION, add_reverse_placements, write_json
from publish_static_asset_review import furniture_browse_categories

INDEX = NEST / "assembly/asset-index.json"
SEED = BUILD / "nest-source-seed.json"
INPUT = DESTINATION / "assets"
RETAINED = "source:retained-placement-variants"
RELOCATION = {
    "source:central-building": "buildings/main/central-building.glb",
    "view:central-building": "buildings/main/central-building.scn",
    "source:pod-building": "buildings/pod/pod-building.glb",
    "view:building-layout": "buildings/building-layout.scn",
    "view:estate-layout": "assembly/estate.tscn",
}
RESIDUALS = {
    "source:door-details": ("buildings/main/door-details.glb", "门扇与门框部件"),
    "source:forest-trail-fixtures": (
        "courtyard/areas/forest/forest-layout/forest-trail-fixtures.glb",
        "林间护栏端柱",
    ),
    "source:water-lilies": (
        "courtyard/areas/waterside/waterside-layout/water-lilies.glb",
        "睡莲原型",
    ),
}


def read(path):
    return json.loads(path.read_text())


def output_file(relative):
    output = NEST / relative
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def residual_owner(path):
    name = Path(path).name
    if name.startswith("LandingTerminalPost"):
        return "source:forest-trail-fixtures"
    if name in {"__ELFIE_INST_GROUP_016", "__ELFIE_INST_GROUP_017"}:
        return "source:water-lilies"
    return "source:door-details"


def migrate_models(entries, originals):
    mesh_nodes = {}
    texture_owners = {}
    for key, entry in entries.items():
        relative = Path(entry["file"])
        if relative.suffix != ".glb" or key in RESIDUALS:
            continue
        with (INPUT / originals[key]).open("rb") as stream:
            with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as binary:
                document, start = read_document(binary)
                output = output_file(relative)
                for image in document.get("images", ()):
                    name = Path(image["uri"]).name
                    if name not in texture_owners:
                        texture_owners[name] = output_file(
                            Path(relative.parts[0]) / "textures" / name
                        )
                        shutil.copyfile(INPUT / "textures" / name, texture_owners[name])
                    image["uri"] = Path(
                        os.path.relpath(texture_owners[name], output.parent)
                    ).as_posix()
                if key == "source:bed-shared":
                    # Import all bed variants as children of the same library root.
                    primary = document["scenes"][document.get("scene", 0)]
                    root = primary["nodes"][0]
                    document["nodes"][root]["children"].extend(
                        node
                        for scene in document["scenes"]
                        for node in scene["nodes"]
                        if node != root
                    )
                    document["scenes"] = [primary]
                    document["scene"] = 0
                header = json.dumps(document, separators=(",", ":")).encode()
                header += b" " * (-len(header) % 4)
                binary.seek(start - 8)
                with output.open("wb") as target:
                    length = 20 + len(header) + len(binary) - binary.tell()
                    target.write(
                        struct.pack(
                            "<4sIIII", b"glTF", 2, length, len(header), 0x4E4F534A
                        )
                    )
                    target.write(header)
                    shutil.copyfileobj(binary, target)
                mesh_nodes[key] = [node for node in document["nodes"] if "mesh" in node]
    with (INPUT / originals[RETAINED]).open("rb") as stream:
        with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as binary:
            document, start = read_document(binary)
            assert not document.get("images")
            for key, (relative, _) in RESIDUALS.items():
                output = output_file(relative)
                library = Library(document, binary, start, output.parent)
                nodes = [
                    {
                        **node,
                        "mesh": library.mesh(
                            node["mesh"], node["extras"]["geometry_id"]
                        ),
                    }
                    for node in document["nodes"]
                    if "mesh" in node
                    and residual_owner(node["extras"]["v044_path"]) == key
                ]
                assert nodes, key
                library.save(output, nodes)
                mesh_nodes[key] = nodes
    assert len(texture_owners) == 79
    return mesh_nodes


def add_assembly(entries, scenes, key, paths, children, bindings):
    scenes[key] = {"file": entries[key]["file"], "paths": paths, "children": children}
    entries[key]["parts"] = [
        {
            "id": asset,
            "count": 8 if asset == "source:pod-building" else 1,
            "unit": "实例",
            "paths": list(placements),
        }
        for asset, placements in bindings.items()
    ] + [{"id": child, "count": 1, "unit": "文件"} for child in children]
    entries[key].pop("members", None)


def main():
    if INDEX.exists() or SEED.exists():
        raise FileExistsError("The formal migration already has an index or seed")
    graph = read(DESTINATION / "file-graph.json")
    native = read(DESTINATION / "native-plan.json")
    old_bindings = read(DESTINATION / "authoring-bindings.json")
    inventory = read(BUILD / "full-inventory/static-nodes.json")
    original_plan = read(CANDIDATE / "assembly-plan.json")
    mesh_at = original_plan["mesh_at_path"]
    aliases = native["geometry_aliases"]
    for alias in aliases.values():
        mesh_at[alias["placement_path"]] = alias["geometry"]
    entries = graph["entries"]
    originals = {key: entry["file"] for key, entry in entries.items()}
    graph["categories"] = furniture_browse_categories(graph["categories"])
    total = next(
        category for category in graph["categories"] if category["id"] == "total"
    )
    total["children"] = [item for item in total["children"] if item["id"] != RETAINED]
    del entries[RETAINED]
    for key, file in RELOCATION.items():
        entries[key]["file"] = file
    for key, (file, title) in RESIDUALS.items():
        entries[key] = {"title": title, "file": file, "kind": "source"}
    models = migrate_models(entries, originals)
    retained_node_owner = {
        node["name"]: key for key in RESIDUALS for node in models[key]
    }
    owner = {}
    prototypes = {}
    for key, nodes in models.items():
        for node in nodes:
            shape = node["extras"]["geometry_id"]
            assert owner.setdefault(shape, key) == key
            prototypes.setdefault(shape, node["name"])
    all_old_shapes = read(DESTINATION / "geometry-owners.json")
    assert set(owner) | set(aliases) == set(all_old_shapes)
    for key, bindings in old_bindings.items():
        for path, placement in bindings.pop(RETAINED, {}).items():
            asset = retained_node_owner[placement["node"]]
            bindings.setdefault(asset, {})[path] = placement
        for part in entries[key].get("parts", ()):
            if part["id"] == RETAINED:
                owners = {
                    asset
                    for asset in RESIDUALS
                    if set(part["paths"]) & bindings.get(asset, {}).keys()
                }
                assert len(owners) == 1, (key, owners)
                part["id"] = owners.pop()

    scenes = native["scenes"]
    central = "view:central-building"
    building = "view:building-layout"
    estate = "view:estate-layout"

    def cover(key):
        return set(scenes[key]["paths"]).union(
            *(cover(child) for child in scenes[key]["children"])
        )

    covered = set().union(*(cover(key) for key in native["assembly_roots"]))
    missed_meshes = sorted(path for path in mesh_at if path not in covered)
    assert len(missed_meshes) == 624

    def mesh_bindings(paths):
        result = defaultdict(dict)
        for path in paths:
            if path in mesh_at:
                shape = mesh_at[path]
                result[owner[shape]][path] = {
                    "node": prototypes[shape],
                    "preserve_material": True,
                }
        return result

    floors = [f"view:central-layout-{floor}" for floor in range(1, 4)]
    old_bindings[central] = mesh_bindings(scenes[central]["paths"])
    add_assembly(
        entries,
        scenes,
        central,
        scenes[central]["paths"],
        floors,
        old_bindings[central],
    )
    building_children = [central] + [
        key
        for key in native["assembly_roots"]
        if key not in {central, "view:courtyard-layout", *floors}
    ]
    old_bindings[building] = mesh_bindings(missed_meshes)
    add_assembly(
        entries,
        scenes,
        building,
        missed_meshes,
        building_children,
        old_bindings[building],
    )
    old_bindings[estate] = {}
    add_assembly(entries, scenes, estate, [], [building, "view:courtyard-layout"], {})
    full_coverage = cover(estate)
    assert full_coverage == covered.union(missed_meshes)
    assert set(mesh_at) <= full_coverage
    for row in inventory:
        if row["type"] == "MultiMeshInstance3D":
            assert row["path"] in full_coverage, row["path"]

    old_previews = read(DESTINATION / "asset-previews.json")
    previews = {}
    for key, entry in entries.items():
        entry["preview"] = key
        entry.pop("usedBy", None)
        record = scenes.get(key, {})
        previous = old_previews.get(key, {})
        available = {node["extras"]["v044_path"] for node in models.get(key, ())}
        focus = entry.pop("focus", [])
        if key in models:
            sample = set(focus or record.get("paths", ())) & available
            focus = sorted(sample) if sample else []
        if key == "source:fountain":
            # The static detail view omits the dormant runtime spray meshes.
            focus = [
                path
                for path in focus
                if not Path(path).name.startswith(
                    ("CentralFlower_", "CentralMainPlume", "OuterJet_")
                )
            ]
        groups = [
            group for group in record.get("groups", ()) if set(group) <= available
        ]
        assert len(groups) == len(record.get("groups", ()))
        entry["focus"] = focus
        previews[key] = {
            "base": previous.get("base", key),
            "groups": groups,
            "front_row": record.get("front_row", False),
            "furniture": entry["file"].startswith("furniture/"),
        }
    add_reverse_placements(entries)
    write_json(
        output_file("assembly/asset-index.json"),
        {"fileGraph": graph, "previews": previews},
    )
    write_json(
        SEED,
        {
            "scenes": {key: scenes[key] for key in old_bindings},
            "bindings": old_bindings,
            "aliases": aliases,
            "visible_nodes": len(mesh_at),
        },
    )
    # Re-read every destination buffer after rebasing texture and scene metadata.
    found = {}
    buffers = defaultdict(set)
    for key in models:
        file = NEST / entries[key]["file"]
        for mesh in glb_meshes(file, buffers):
            assert owner[mesh["shape"]] == key
            assert found.setdefault(mesh["shape"], mesh["payload"]) == mesh["payload"]
    assert set(found) == set(owner)
    print(
        f"NEST_FORMAL_GLBS={len(models)} unique_shapes={len(found)} scene_seed={len(old_bindings)}"
    )


if __name__ == "__main__":
    main()
