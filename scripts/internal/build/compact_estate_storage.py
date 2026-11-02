"""Reclaim unreachable estate mesh data and share exact binary payloads.

Preserves all nodes, materials, textures, metadata and physics shapes. Only
standard mesh/accessor/view references and OMI mesh references are remapped.
"""

from __future__ import annotations

import copy
import hashlib

SUPPORTED = {
    "KHR_lights_punctual",
    "KHR_texture_transform",
    "OMI_physics_body",
    "OMI_physics_shape",
    "KHR_materials_clearcoat",
    "KHR_materials_emissive_strength",
    "KHR_materials_ior",
    "KHR_materials_iridescence",
    "KHR_materials_sheen",
    "KHR_materials_specular",
    "KHR_materials_transmission",
    "KHR_materials_unlit",
    "KHR_materials_volume",
}


def compact_storage(source: dict, binary: bytes) -> tuple[dict, bytes, dict]:
    """Return a new graph and verify that each retained view remains byte exact."""
    if set(source.get("extensionsUsed", [])) - SUPPORTED:
        raise ValueError("Unknown extension needs explicit reference handling")
    if source.get("animations") or source.get("skins"):
        raise ValueError("Animated/skinned storage is outside this static asset scope")
    if len(source["buffers"]) != 1 or "uri" in source["buffers"][0]:
        raise ValueError("Expected one embedded buffer")
    if any(a.get("sparse") or a.get("extensions") for a in source["accessors"]):
        raise ValueError("Sparse/extended accessors require separate handling")
    doc = copy.deepcopy(source)
    used_meshes = {n["mesh"] for n in doc["nodes"] if "mesh" in n}
    shapes = doc.get("extensions", {}).get("OMI_physics_shape", {}).get("shapes", [])
    physics = [s[k] for s in shapes for k in ("trimesh", "convex") if k in s]
    used_meshes.update(s["mesh"] for s in physics if "mesh" in s)
    mesh_map = {old: new for new, old in enumerate(sorted(used_meshes))}
    doc["meshes"] = [doc["meshes"][i] for i in sorted(used_meshes)]
    for holder in doc["nodes"] + physics:
        if "mesh" in holder:
            holder["mesh"] = mesh_map[holder["mesh"]]
    primitives = [p for m in doc["meshes"] for p in m["primitives"]]
    if any(p.get("extensions") or p.get("targets") for p in primitives):
        raise ValueError("Extended/morph primitives require separate handling")
    used_accessors = {a for p in primitives for a in p["attributes"].values()}
    used_accessors.update(p["indices"] for p in primitives if "indices" in p)
    accessor_map = {old: new for new, old in enumerate(sorted(used_accessors))}
    doc["accessors"] = [doc["accessors"][i] for i in sorted(used_accessors)]
    for primitive in primitives:
        primitive["attributes"] = {
            key: accessor_map[value] for key, value in primitive["attributes"].items()
        }
        if "indices" in primitive:
            primitive["indices"] = accessor_map[primitive["indices"]]
    used_views = {a["bufferView"] for a in doc["accessors"]}
    used_views.update(
        i["bufferView"] for i in doc.get("images", []) if "bufferView" in i
    )
    view_map = {old: new for new, old in enumerate(sorted(used_views))}
    doc["bufferViews"] = [doc["bufferViews"][i] for i in sorted(used_views)]
    for holder in doc["accessors"] + doc.get("images", []):
        if "bufferView" in holder:
            holder["bufferView"] = view_map[holder["bufferView"]]
    payload = bytearray()
    locations: dict[bytes, tuple[int, int]] = {}
    for view in doc["bufferViews"]:
        offset, length = view.get("byteOffset", 0), view["byteLength"]
        if view.get("buffer", 0) != 0 or offset < 0 or offset + length > len(binary):
            raise ValueError("Invalid buffer range")
        chunk = binary[offset : offset + length]
        digest = hashlib.sha256(chunk).digest()
        if digest in locations:
            previous, size = locations[digest]
            if size != length or payload[previous : previous + size] != chunk:
                raise ValueError("Payload digest collision")
        else:
            payload.extend(bytes(-len(payload) % 4))
            previous = len(payload)
            locations[digest] = (previous, length)
            payload.extend(chunk)
        view["byteOffset"] = previous
    doc["buffers"][0]["byteLength"] = len(payload)
    for old, new in view_map.items():
        a, b = source["bufferViews"][old], doc["bufferViews"][new]
        length = a["byteLength"]
        if (
            binary[a.get("byteOffset", 0) : a.get("byteOffset", 0) + length]
            != payload[b["byteOffset"] : b["byteOffset"] + length]
        ):
            raise ValueError("Retained bytes changed")
    return (
        doc,
        bytes(payload),
        {
            "removed_meshes": len(source["meshes"]) - len(doc["meshes"]),
            "removed_accessors": len(source["accessors"]) - len(doc["accessors"]),
            "retained_views_verified": len(view_map),
            "mesh_map": mesh_map,
        },
    )
