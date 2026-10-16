"""Hash selected GLB content, resolving indices instead of hashing its container."""

import hashlib
import json
import struct
from functools import cache, lru_cache
from pathlib import Path


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@lru_cache(maxsize=128)
def node_contents(path: str, modified: int, size: int):
    del modified, size
    with Path(path).open("rb") as stream:
        header = stream.read(20)
        length = struct.unpack_from("<I", header, 12)[0]
        doc = json.loads(stream.read(length))
        chunk = stream.read(8)
        binary = stream.read() if chunk else b""
    if doc.get("skins") or doc.get("animations") or doc.get("extensionsRequired"):
        raise ValueError(
            "Animated, skinned or required-extension models need explicit object review"
        )

    @cache
    def view(index):
        value = doc["bufferViews"][index]
        if value.get("buffer", 0) != 0 or doc.get("buffers", [{}])[0].get("uri"):
            raise ValueError("External geometry needs explicit object review")
        start = value.get("byteOffset", 0)
        data = binary[start : start + value["byteLength"]]
        if len(data) != value["byteLength"]:
            raise ValueError("Truncated geometry buffer")
        return data

    @cache
    def accessor(index):
        value = doc["accessors"][index]
        if value.get("sparse"):
            raise ValueError("Sparse geometry needs explicit object review")
        component = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}[
            value["componentType"]
        ]
        shape = value["type"]
        if shape.startswith("MAT"):
            columns = int(shape[-1])
            width = ((columns * component + 3) // 4 * 4) * columns
        else:
            width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[shape] * component
        count = value["count"]
        if "bufferView" in value:
            data = view(value["bufferView"])
            offset = value.get("byteOffset", 0)
            stride = doc["bufferViews"][value["bufferView"]].get("byteStride", width)
            if offset + max(0, count - 1) * stride + (width if count else 0) > len(
                data
            ):
                raise ValueError("Truncated accessor")
            packed = (
                data[offset : offset + count * width]
                if stride == width
                else b"".join(
                    data[offset + i * stride : offset + i * stride + width]
                    for i in range(count)
                )
            )
        else:
            packed = bytes(count * width)
        return {
            "componentType": value["componentType"],
            "type": shape,
            "count": count,
            "normalized": value.get("normalized", False),
            "bytes": hashlib.sha256(packed).hexdigest(),
        }

    @cache
    def texture(index):
        value = dict(doc["textures"][index])
        if value.get("extensions"):
            raise ValueError("Extended textures need explicit object review")
        image = dict(doc["images"][value["source"]])
        image.pop("name", None)
        if "bufferView" in image:
            image["bufferView"] = hashlib.sha256(view(image["bufferView"])).hexdigest()
        elif not image.get("uri", "").startswith("data:"):
            raise ValueError("External textures need explicit object review")
        value["source"] = image
        value.pop("name", None)
        if "sampler" in value:
            value["sampler"] = doc["samplers"][value["sampler"]]
        return value

    def textures(value):
        if isinstance(value, list):
            return [textures(v) for v in value]
        if not isinstance(value, dict):
            return value
        return {
            k: {**textures(v), "index": texture(v["index"])}
            if k.endswith("Texture") and isinstance(v, dict) and "index" in v
            else textures(v)
            for k, v in value.items()
        }

    @cache
    def mesh(index):
        value = json.loads(json.dumps(doc["meshes"][index]))
        value.pop("name", None)
        for primitive in value["primitives"]:
            if primitive.get("extensions"):
                raise ValueError("Extended primitives need explicit object review")
            primitive["attributes"] = {
                k: accessor(v) for k, v in primitive["attributes"].items()
            }
            if "indices" in primitive:
                primitive["indices"] = accessor(primitive["indices"])
            if "material" in primitive:
                material = dict(doc["materials"][primitive["material"]])
                material.pop("name", None)
                primitive["material"] = textures(material)
            if "targets" in primitive:
                primitive["targets"] = [
                    {k: accessor(v) for k, v in target.items()}
                    for target in primitive["targets"]
                ]
        return digest(value)

    result = {}

    def visit(index, inherited, ancestors):
        node = doc["nodes"][index]
        properties = {**inherited, **node.get("extras", {})}
        transforms = ancestors + [
            {
                k: node[k]
                for k in ("matrix", "translation", "rotation", "scale")
                if k in node
            }
        ]
        if "mesh" in node:
            result[index] = digest(
                {
                    "mesh": mesh(node["mesh"]),
                    "transforms": transforms,
                    "properties": properties,
                    "weights": node.get("weights"),
                    "extensions": node.get("extensions"),
                }
            )
        for child in node.get("children", []):
            visit(child, properties, transforms)

    for index in doc["scenes"][doc.get("scene", 0)]["nodes"]:
        visit(index, {}, [])
    return result


def content_digest(root, file, nodes):
    path = (root / file).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Model unavailable")
    stat = path.stat()
    contents = node_contents(str(path), stat.st_mtime_ns, stat.st_size)
    return digest(sorted(contents[index] for index in nodes))
