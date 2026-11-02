"""Share identical GLB resources without changing binary data or scene placement.

Run after the estate's MultiMesh compatibility conversion. Names on shared
resources are labels only; node names, metadata, transforms and materials with
different values are retained. OMI collision mesh indices are remapped too.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import struct
from pathlib import Path


def _share(document: dict, field: str) -> dict[int, int]:
    unique: list[dict] = []
    indices: dict[str, int] = {}
    mapping: dict[int, int] = {}
    for old_index, resource in enumerate(document.get(field, [])):
        key = json.dumps(
            {k: v for k, v in resource.items() if k != "name"}, sort_keys=True
        )
        if key not in indices:
            indices[key] = len(unique)
            unique.append(resource)
        mapping[old_index] = indices[key]
    document[field] = unique
    return mapping


def _remap_material_textures(value: object, mapping: dict[int, int]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "extras":
                continue  # Application metadata is not a glTF texture reference.
            if key.endswith("Texture") and isinstance(child, dict) and "index" in child:
                child["index"] = mapping[child["index"]]
            _remap_material_textures(child, mapping)
    elif isinstance(value, list):
        for child in value:
            _remap_material_textures(child, mapping)


def share_resources(source: dict) -> dict:
    """Return an independent, equivalent resource graph with shared references."""
    document = copy.deepcopy(source)
    image_map = _share(document, "images")
    for texture in document.get("textures", []):
        if "source" in texture:
            texture["source"] = image_map[texture["source"]]
        for name, extension in texture.get("extensions", {}).items():
            if name not in {
                "KHR_texture_basisu",
                "EXT_texture_webp",
                "MSFT_texture_dds",
            }:
                raise ValueError(f"Unsupported texture extension: {name}")
            if "source" in extension:
                extension["source"] = image_map[extension["source"]]
    texture_map = _share(document, "textures")
    _remap_material_textures(document.get("materials", []), texture_map)
    material_map = _share(document, "materials")
    for mesh in document.get("meshes", []):
        for primitive in mesh["primitives"]:
            if "extensions" in primitive:
                raise ValueError(
                    "Primitive extensions need explicit reference handling"
                )
            if "material" in primitive:
                primitive["material"] = material_map[primitive["material"]]
    mesh_map = _share(document, "meshes")
    for node in document.get("nodes", []):
        if "mesh" in node:
            node["mesh"] = mesh_map[node["mesh"]]
    physics = document.get("extensions", {}).get("OMI_physics_shape", {})
    for shape in physics.get("shapes", []):
        for shape_type in ("trimesh", "convex"):
            geometry = shape.get(shape_type, {})
            if "mesh" in geometry:
                geometry["mesh"] = mesh_map[geometry["mesh"]]
    return document


def optimize(source: Path, output: Path) -> dict:
    if source.resolve() == output.resolve():
        raise ValueError("Use a separate output; retain the original asset")
    data = source.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", data)
    if magic != b"glTF" or version != 2 or length != len(data):
        raise ValueError("Invalid GLB 2 header")
    json_length, chunk_type = struct.unpack_from("<I4s", data, 12)
    if chunk_type != b"JSON":
        raise ValueError("Missing first JSON chunk")
    original = json.loads(data[20 : 20 + json_length])
    document = share_resources(original)
    payload = json.dumps(document, separators=(",", ":"), ensure_ascii=False).encode()
    payload += b" " * (-len(payload) % 4)
    remaining_chunks = data[20 + json_length :]
    encoded = (
        struct.pack("<4sII", b"glTF", 2, 20 + len(payload) + len(remaining_chunks))
        + struct.pack("<I4s", len(payload), b"JSON")
        + payload
        + remaining_chunks
    )
    output.write_bytes(encoded)
    return {
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "output_sha256": hashlib.sha256(encoded).hexdigest(),
        "source_bytes": len(data),
        "output_bytes": len(encoded),
        "unchanged_binary_chunks_sha256": hashlib.sha256(remaining_chunks).hexdigest(),
        "resources": {
            field: [len(original.get(field, [])), len(document.get(field, []))]
            for field in ("images", "textures", "materials", "meshes", "nodes")
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(optimize(args.source, args.output), indent=2))


if __name__ == "__main__":
    main()
