"""Extract a self-contained GLB without changing geometry or world transforms."""

import copy
import json
import struct
from functools import cache
from pathlib import Path
from typing import Any, Iterable

from devtools.asset_design.glb_resources import IMAGE_MIMES, read_glb, resource_bytes


def extract_glb(
    path: Path, selected: Iterable[int], anchors: Iterable[int] = ()
) -> tuple[bytes, dict[int, int]]:
    doc, binary = read_glb(path)
    if doc.get("animations") or doc.get("skins") or doc.get("extensionsRequired"):
        raise ValueError(
            "Animated or extended models require explicit extraction support"
        )
    output = {"asset": copy.deepcopy(doc["asset"]), "scene": 0}
    if doc.get("extensionsUsed"):
        output["extensionsUsed"] = copy.deepcopy(doc["extensionsUsed"])
    tables: dict[str, list[dict[str, Any]]] = {}
    maps: dict[str, dict[int, int]] = {}
    payload = bytearray()

    def append(chunk):
        payload.extend(bytes(-len(payload) % 4))
        value = {"buffer": 0, "byteOffset": len(payload), "byteLength": len(chunk)}
        payload.extend(chunk)
        return value

    @cache
    def buffer(index):
        value = doc["buffers"][index]
        if value.get("uri"):
            return resource_bytes(path, value["uri"])
        if index != 0:
            raise ValueError("Only the first buffer can use the GLB binary chunk")
        return binary

    def take(kind, index, convert):
        mapping = maps.setdefault(kind, {})
        if index not in mapping:
            value = convert(copy.deepcopy(doc[kind][index]))
            mapping[index] = len(tables.setdefault(kind, []))
            tables[kind].append(value)
        return mapping[index]

    def view(index):
        def convert(value):
            start = value.get("byteOffset", 0)
            chunk = buffer(value.get("buffer", 0))[start : start + value["byteLength"]]
            if len(chunk) != value["byteLength"]:
                raise ValueError("Truncated binary input")
            value.update(append(chunk))
            return value

        return take("bufferViews", index, convert)

    def accessor(index):
        def convert(value):
            if value.get("sparse"):
                raise ValueError("Sparse accessor extraction unsupported")
            if "bufferView" in value:
                value["bufferView"] = view(value["bufferView"])
            return value

        return take("accessors", index, convert)

    def texture(index):
        def convert_image(value):
            if "bufferView" in value:
                value["bufferView"] = view(value["bufferView"])
            elif not value.get("uri", "").startswith("data:"):
                uri = value.pop("uri", "")
                suffix = Path(uri).suffix
                if suffix not in IMAGE_MIMES:
                    raise ValueError("Unsupported external image resource")
                chunk = resource_bytes(path, uri)
                value.setdefault("mimeType", IMAGE_MIMES[suffix])
                value["bufferView"] = len(tables.setdefault("bufferViews", []))
                tables["bufferViews"].append(append(chunk))
            return value

        def convert(value):
            if value.get("extensions"):
                raise ValueError("Extended texture extraction unsupported")
            value["source"] = take("images", value["source"], convert_image)
            if "sampler" in value:
                value["sampler"] = take("samplers", value["sampler"], lambda v: v)
            return value

        return take("textures", index, convert)

    def material(value):
        if isinstance(value, list):
            return [material(v) for v in value]
        if not isinstance(value, dict):
            return value
        return {
            k: {**material(v), "index": texture(v["index"])}
            if k.endswith("Texture") and isinstance(v, dict) and "index" in v
            else material(v)
            for k, v in value.items()
        }

    def mesh(value):
        for primitive in value["primitives"]:
            if primitive.get("extensions"):
                raise ValueError("Extended mesh extraction unsupported")
            primitive["attributes"] = {
                k: accessor(v) for k, v in primitive["attributes"].items()
            }
            if "indices" in primitive:
                primitive["indices"] = accessor(primitive["indices"])
            if "material" in primitive:
                primitive["material"] = take(
                    "materials", primitive["material"], material
                )
            if "targets" in primitive:
                primitive["targets"] = [
                    {k: accessor(v) for k, v in t.items()} for t in primitive["targets"]
                ]
        return value

    selected = set(selected)
    required = selected | set(anchors)
    parent = {
        child: i
        for i, node in enumerate(doc["nodes"])
        for child in node.get("children", [])
    }
    for index in list(required):
        trail = set()
        while index in parent:
            if index in trail:
                raise ValueError("Cyclic scene hierarchy")
            trail.add(index)
            index = parent[index]
            required.add(index)
    mapping = {old: new for new, old in enumerate(sorted(required))}
    nodes = []
    for old in sorted(required):
        node = copy.deepcopy(doc["nodes"][old])
        if "mesh" in node:
            if old in selected:
                node["mesh"] = take("meshes", node["mesh"], mesh)
            else:
                del node["mesh"]
        if "children" in node:
            node["children"] = [mapping[i] for i in node["children"] if i in required]
        if "camera" in node or node.get("skin") is not None or node.get("extensions"):
            raise ValueError(
                "Camera, skin or extended node needs explicit extraction support"
            )
        nodes.append(node)
    output["nodes"] = nodes
    output["scenes"] = [
        {
            "nodes": [
                mapping[i]
                for i in doc["scenes"][doc.get("scene", 0)]["nodes"]
                if i in mapping
            ]
        }
    ]
    output.update(tables)
    if payload:
        output["buffers"] = [{"byteLength": len(payload)}]
    encoded = json.dumps(output, ensure_ascii=False, separators=(",", ":")).encode()
    encoded += b" " * (-len(encoded) % 4)
    payload.extend(bytes(-len(payload) % 4))
    tail = struct.pack("<II", len(payload), 0x004E4942) + payload if payload else b""
    result = (
        struct.pack(
            "<5I",
            0x46546C67,
            2,
            20 + len(encoded) + len(tail),
            len(encoded),
            0x4E4F534A,
        )
        + encoded
        + tail
    )
    return result, mapping
