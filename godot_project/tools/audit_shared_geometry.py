"""Audit geometry ownership across Nest GLBs, ignoring materials and placement."""

import hashlib
import json
import mmap
import struct
from collections import Counter, defaultdict
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build/godot-asset-migration"
AUTHORING = BUILD / "exported-v044-native/authoring"
NEST = ROOT / "godot_project/nest"
COMPONENT_BYTES = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
ELEMENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def glb_meshes(path, stored_buffers):
    with (
        path.open("rb") as stream,
        mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data,
    ):
        magic, version, length, json_size, kind = struct.unpack_from("<4sIIII", data)
        if (magic, version, length, kind) != (b"glTF", 2, len(data), 0x4E4F534A):
            raise ValueError(f"Unsupported GLB header: {path}")
        doc = json.loads(data[20 : 20 + json_size])
        binary_size, binary_kind = struct.unpack_from("<II", data, 20 + json_size)
        binary_start = 28 + json_size
        if binary_kind != 0x004E4942 or binary_start + binary_size != len(data):
            raise ValueError(f"Missing GLB binary chunk: {path}")

        used_views = set()

        @cache
        def accessor(index):
            item = doc["accessors"][index]
            view_id = item["bufferView"]
            used_views.add(view_id)
            view = doc["bufferViews"][view_id]
            if (
                item.get("sparse")
                or view.get("extensions")
                or view.get("buffer", 0) != 0
            ):
                raise ValueError(f"Unverified accessor encoding: {path} #{index}")
            width = COMPONENT_BYTES[item["componentType"]] * ELEMENTS[item["type"]]
            stride = view.get("byteStride", width)
            start = view.get("byteOffset", 0) + item.get("byteOffset", 0)
            count = item["count"]
            end = start + ((count - 1) * stride + width if count else 0)
            if end > min(binary_size, view.get("byteOffset", 0) + view["byteLength"]):
                raise ValueError(f"Out-of-bounds accessor: {path} #{index}")
            begin, end = binary_start + start, binary_start + end
            digest = hashlib.sha256()
            if stride == width:
                with memoryview(data) as view_bytes:
                    digest.update(view_bytes[begin:end])
            else:
                for offset in range(begin, end, stride):
                    digest.update(data[offset : offset + width])
            signature = (
                item["componentType"],
                item["type"],
                count,
                item.get("normalized", False),
                digest.hexdigest(),
            )
            return signature, width * count

        def hash_layout(value):
            return hashlib.sha256(
                json.dumps(value, sort_keys=True).encode()
            ).hexdigest()

        nodes_by_mesh = defaultdict(list)
        for node in doc["nodes"]:
            if "mesh" in node:
                extras = node.get("extras", {})
                nodes_by_mesh[node["mesh"]].append(
                    extras.get("v044_path") or node.get("name", "")
                )
        result = []
        for index, mesh in enumerate(doc["meshes"]):
            shapes = []
            payloads = []
            geometry_bytes = 0
            for part in mesh["primitives"]:
                if part.get("extensions"):
                    raise ValueError(f"Unverified primitive extension: {path} #{index}")
                attrs = {
                    key: accessor(value)[0] for key, value in part["attributes"].items()
                }
                targets = [
                    {key: accessor(value)[0] for key, value in target.items()}
                    for target in part.get("targets", [])
                ]
                indices = accessor(part["indices"])[0] if "indices" in part else None
                topology = (part.get("mode", 4), indices)
                shapes.append(
                    (
                        topology,
                        attrs["POSITION"],
                        [target.get("POSITION") for target in targets],
                    )
                )
                payloads.append((topology, attrs, targets))
                geometry_bytes += sum(
                    accessor(value)[1] for value in part["attributes"].values()
                )
                if "indices" in part:
                    geometry_bytes += accessor(part["indices"])[1]
            result.append(
                {
                    "file": str(path.relative_to(ROOT)),
                    "mesh": index,
                    "shape": hash_layout(shapes),
                    "payload": hash_layout(payloads),
                    "attribute_and_index_bytes": geometry_bytes,
                    "material_slots": [
                        part.get("material") for part in mesh["primitives"]
                    ],
                    "placements": nodes_by_mesh[index],
                }
            )
        for view_id in used_views:
            view = doc["bufferViews"][view_id]
            offset = view.get("byteOffset", 0)
            size = view["byteLength"]
            with memoryview(data) as view_bytes:
                checksum = hashlib.sha256(
                    view_bytes[binary_start + offset : binary_start + offset + size]
                ).hexdigest()
            stored_buffers[size, checksum].add((str(path.relative_to(ROOT)), offset))
        return result


def summarize(records):
    by_shape = defaultdict(list)
    by_payload = defaultdict(list)
    for record in records:
        by_shape[record["shape"]].append(record)
        by_payload[record["payload"]].append(record)
    duplicates = [group for group in by_shape.values() if len(group) > 1]
    return {
        "meshes": len(records),
        "geometry_prototypes": len(by_shape),
        "duplicate_mesh_records": len(records) - len(by_shape),
        "exact_render_payload_duplicates": len(records) - len(by_payload),
        "shapes_in_multiple_files": sum(
            len({item["file"] for item in group}) > 1 for group in duplicates
        ),
        "additional_logical_payload_bytes": sum(
            sum(item["attribute_and_index_bytes"] for item in group[1:])
            for group in by_payload.values()
        ),
        "duplicate_groups": sorted(duplicates, key=len, reverse=True),
    }


def shared_libraries(authored):
    inventory = {
        node["path"]: node
        for node in json.loads((BUILD / "full-inventory/static-nodes.json").read_text())
    }
    bindings = {
        item["id"]: item["paths"]
        for item in json.loads((BUILD / "static-export-bindings.json").read_text())[
            "items"
        ]
    }
    groups = {}
    for asset, paths in bindings.items():
        if not asset.startswith("common-"):
            continue
        extras = [inventory[path]["extras"] for path in paths]
        groups[asset] = {
            "mesh_nodes": len(paths),
            "design_templates": len({item["designTemplate"] for item in extras}),
            "placements": len(
                {
                    (item["designTemplate"], item.get("designTemplateInstance"))
                    for item in extras
                }
            ),
        }
    forest = set(bindings["forest-library"])
    plants = set(bindings["plant-library"])
    groups["courtyard-prototypes"] = {
        "forest_entries": len(forest),
        "plant_entries": len(plants),
        "same_source_nodes_in_both": len(forest & plants),
        "unique_source_nodes": len(forest | plants),
    }
    modules = defaultdict(Counter)
    variants = defaultdict(set)
    for mesh in authored:
        if Path(mesh["file"]).name != "pod-building.glb":
            continue
        for path in mesh["placements"]:
            module = inventory[path]["extras"]["module"]
            modules[module][mesh["payload"]] += 1
            variants[mesh["shape"]].add(tuple(mesh["material_slots"]))
    groups["shared-pod"] = {
        "module_count": len(modules),
        "mesh_parts_per_module": {
            module: sum(meshes.values()) for module, meshes in sorted(modules.items())
        },
        "same_mesh_payload_multiset": bool(modules)
        and all(meshes == modules["M01"] for meshes in modules.values()),
        "shapes_with_material_variants": sum(
            len(materials) > 1 for materials in variants.values()
        ),
    }
    return groups


def run():
    files = sorted(AUTHORING.glob("*.glb"))
    sources = sorted(NEST.rglob("*.glb"))
    if not files or not sources:
        raise ValueError("Expected authoring exports and Nest sources")
    authoring_buffers = defaultdict(set)
    source_buffers = defaultdict(set)
    authored = [
        record for file in files for record in glb_meshes(file, authoring_buffers)
    ]
    active = [record for file in sources for record in glb_meshes(file, source_buffers)]
    authored_report = summarize(authored)
    source_report = summarize(active)
    for stats, buffers in (
        (authored_report, authoring_buffers),
        (source_report, source_buffers),
    ):
        stats["exact_duplicate_geometry_buffer_bytes"] = sum(
            size * (len(positions) - 1)
            for (size, _digest), positions in buffers.items()
        )
    per_file = []
    for file in files:
        group = [
            item for item in authored if item["file"] == str(file.relative_to(ROOT))
        ]
        stats = summarize(group)
        per_file.append(
            {
                "file": file.name,
                "bytes": file.stat().st_size,
                **{k: v for k, v in stats.items() if k != "duplicate_groups"},
            }
        )
    report = {
        "scope": "Exact accessor geometry and topology, irrespective of material, object name and node placement. Alternate vertex orders, baked transforms and changed topology require separate equivalence proof. Logical payload bytes may share buffer views and are not a disk-saving estimate.",
        "authoring_files": len(files),
        "authoring_glb_bytes": sum(file.stat().st_size for file in files),
        "authoring_blend_bytes": sum(
            file.stat().st_size for file in AUTHORING.glob("*.blend")
        ),
        "authoring": authored_report,
        "nest_source_files": len(sources),
        "nest_sources": source_report,
        "per_authoring_file": per_file,
        "shared_libraries": shared_libraries(authored),
    }
    target = BUILD / "geometry-reuse-audit.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    for label, values in (
        ("authoring", authored_report),
        ("nest_sources", source_report),
    ):
        print(label, {k: v for k, v in values.items() if k != "duplicate_groups"})
    print(target)
    return report


def require_unique_authoring_geometry():
    report = run()
    duplicates = report["authoring"]["duplicate_mesh_records"]
    if duplicates:
        raise SystemExit(
            f"TOP 1 geometry ownership failed: {duplicates} duplicate mesh records. "
            "See geometry-reuse-audit.json for the owning files and placements."
        )
    return report


if __name__ == "__main__":
    run()
