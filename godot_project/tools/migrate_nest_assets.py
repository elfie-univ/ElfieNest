"""Seed the formal split estate from the audited V044 extraction once."""

import copy
import hashlib
import json
import mmap
import os
import shutil
import struct
import sys
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


def consolidate_ground_sources(mapping_path):
    """Fold the evaluated, corrected ground into its existing source GLBs once.

    The mapping is extracted from native scenes, not inferred from matching heights.
    Runtime chunks subsequently derive exclusively from these corrected sources.
    """
    rows = read(Path(mapping_path))
    index = read(INDEX)
    entries = index["fileGraph"]["entries"]
    ground = NEST / entries["source:shared-ground"]["file"]
    ground_binary = bytearray(ground.read_bytes())
    document, start = read_document(ground_binary)
    payload = bytearray(ground_binary[start:])
    patch_nodes = {
        node["extras"]["v044_path"]: node
        for node in document["nodes"]
        if "mesh" in node
    }
    groups = defaultdict(list)
    for row in rows:
        groups[row["source"]].append(row)
    owners = {}
    inputs = {}
    for key, entry in entries.items():
        if entry["kind"] != "source":
            continue
        path = NEST / entry["file"]
        binary = path.read_bytes()
        doc, offset = read_document(binary)
        for node in doc["nodes"]:
            if "mesh" in node and node["extras"].get("source_name") in groups:
                name = node["extras"]["source_name"]
                assert name not in owners, name
                owners[name] = (key, node)
                inputs[key] = (path, doc, binary, offset)
    assert owners.keys() == groups.keys(), groups.keys() - owners.keys()

    def data_at(accessor):
        a = document["accessors"][accessor]
        view = document["bufferViews"][a["bufferView"]]
        width = {5121: 1, 5123: 2, 5125: 4, 5126: 4}[a["componentType"]] * {
            "SCALAR": 1,
            "VEC2": 2,
            "VEC3": 3,
            "VEC4": 4,
        }[a["type"]]
        begin = view.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = view.get("byteStride", width)
        return b"".join(
            payload[begin + i * stride : begin + i * stride + width]
            for i in range(a["count"])
        )

    def append_accessor(example, data, count, bounds=None):
        payload.extend(b"\0" * (-len(payload) % 4))
        view = len(document["bufferViews"])
        document["bufferViews"].append(
            {"buffer": 0, "byteOffset": len(payload), "byteLength": len(data)}
        )
        payload.extend(data)
        record = {
            k: v
            for k, v in example.items()
            if k not in {"bufferView", "byteOffset", "min", "max"}
        }
        record.update(bufferView=view, count=count)
        if bounds is not None:
            record.update(min=bounds[0], max=bounds[1])
        document["accessors"].append(record)
        return len(document["accessors"]) - 1

    plan = {"sources": [], "removed": [row["path"] for row in rows]}
    replacements = {}
    for name, patches in groups.items():
        key, original = owners[name]
        surfaces = defaultdict(list)
        for row in patches:
            surfaces[row["surface"]].append(row)
        primitives, materials, layers, provenance = [], [], [], []
        for _, parts in sorted(surfaces.items()):
            source_primitives = [
                document["meshes"][patch_nodes[row["path"]]["mesh"]]["primitives"][0]
                for row in parts
            ]
            first = source_primitives[0]
            assert all(
                pr["attributes"].keys() == first["attributes"].keys()
                and pr["material"] == first["material"]
                for pr in source_primitives
            )
            assert len({row["layers"] for row in parts}) == 1
            attributes = {}
            for attribute in first["attributes"]:
                records = [
                    document["accessors"][pr["attributes"][attribute]]
                    for pr in source_primitives
                ]
                assert (
                    len(
                        {
                            (a["type"], a["componentType"], a.get("normalized", False))
                            for a in records
                        }
                    )
                    == 1
                )
                raw = b"".join(
                    data_at(pr["attributes"][attribute]) for pr in source_primitives
                )
                bounds = (
                    (
                        [min(a["min"][j] for a in records) for j in range(3)],
                        [max(a["max"][j] for a in records) for j in range(3)],
                    )
                    if attribute == "POSITION"
                    else None
                )
                attributes[attribute] = append_accessor(
                    records[0], raw, sum(a["count"] for a in records), bounds
                )
            indices, vertex_offset = [], 0
            for pr in source_primitives:
                a = document["accessors"][pr["indices"]]
                fmt = {5121: "B", 5123: "H", 5125: "I"}[a["componentType"]]
                indices.extend(
                    v[0] + vertex_offset
                    for v in struct.iter_unpack("<" + fmt, data_at(pr["indices"]))
                )
                vertex_offset += document["accessors"][pr["attributes"]["POSITION"]][
                    "count"
                ]
            idx = append_accessor(
                {"componentType": 5125, "type": "SCALAR"},
                struct.pack("<" + "I" * len(indices), *indices),
                len(indices),
            )
            primitives.append(
                {
                    "attributes": attributes,
                    "indices": idx,
                    "material": first["material"],
                }
            )
            extras = patch_nodes[parts[0]["path"]]["extras"]
            materials.append(extras.get("nest_materials", [{}])[0])
            layers.append(parts[0]["layers"])
            provenance.append(parts[0]["path"])
        node = copy.deepcopy(original)
        node["mesh"] = len(document["meshes"])
        document["meshes"].append({"primitives": primitives})
        node["extras"]["nest_render_partition"] = {
            "cell_size": 8.0,
            "surface_layers": layers,
        }
        node["extras"]["geometry_id"] = hashlib.sha256(
            json.dumps(primitives, sort_keys=True).encode()
        ).hexdigest()
        node["extras"].pop("review_visible", None)
        node["extras"].pop("nest_materials", None)
        if any(materials):
            node["extras"]["nest_materials"] = materials
        replacements[name] = node
        plan["sources"].append(
            {
                "asset": key,
                "file": entries[key]["file"],
                "node": node["name"],
                "path": node["extras"]["v044_path"],
                "materials_from": provenance,
                "layers": layers,
            }
        )

    class FormalLibrary(Library):
        def select(self, source, binary, offset, directory):
            self.source, self.binary, self.binary_start = source, binary, offset
            self.directory = directory
            self.index = self.indices.setdefault(str(directory), {})

        def image(self, number):
            def relocate(record):
                assert "uri" in record
                image = (self.directory / record["uri"]).resolve()
                assert image.is_file()
                record["uri"] = Path(os.path.relpath(image, self.textures)).as_posix()
                return record

            return self.copy_index("images", number, relocate)

    for key, (path, doc, binary, offset) in inputs.items():
        library = FormalLibrary(doc, binary, offset, path.parent)
        library.indices = {}
        nodes = []
        for original in doc["nodes"]:
            if "mesh" not in original or original["extras"].get(
                "source_name", ""
            ).startswith("GroundPatch_"):
                continue
            name = original["extras"].get("source_name")
            node = copy.deepcopy(replacements.get(name, original))
            if name in replacements:
                library.select(document, payload, 0, ground.parent)
            else:
                library.select(doc, binary, offset, path.parent)
            node["mesh"] = library.mesh(node["mesh"], node["extras"]["geometry_id"])
            nodes.append(node)
        library.save(path, nodes)
        entries[key]["focus"] = [node["extras"]["v044_path"] for node in nodes]
    # Generated placements are no longer formal file-internal components.
    removed = set(plan["removed"])
    for entry in entries.values():
        for part in entry.get("parts", []):
            for field in ("paths", "targetPaths"):
                if field in part:
                    part[field] = [path for path in part[field] if path not in removed]
    for entry in entries.values():
        entry.pop("usedBy", None)
    add_reverse_placements(entries)
    write_json(INDEX, index)
    write_json(Path(mapping_path).with_name("consolidation-plan.json"), plan)
    print(
        f"Ground sources consolidated: {len(groups)}; removed stored chunks: {len(rows)}"
    )


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
    if len(sys.argv) == 3 and sys.argv[1] == "--consolidate-ground":
        consolidate_ground_sources(sys.argv[2])
    else:
        main()
