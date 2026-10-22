"""Hash selected GLB content, resolving indices instead of hashing its container."""

import hashlib
import json
from functools import cache, lru_cache
from pathlib import Path
from typing import Iterable, Optional, Union

from devtools.asset_design.glb_resources import (
    IMAGE_MIMES,
    dependency_signature,
    read_glb,
    resource_bytes,
)


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def node_contents(
    path: str,
    modified: int,
    size: int,
    root: Optional[Union[Path, str]] = None,
) -> dict[int, str]:
    stat = Path(path).stat()
    doc = _document(path, modified, size, stat.st_ctime_ns)
    signature = dependency_signature(path, doc, root)
    return _node_contents(path, modified, size, stat.st_ctime_ns, signature, root)


@lru_cache(maxsize=512)
def _document(path: str, modified: int, size: int, changed: int) -> dict:
    del modified, size, changed
    return read_glb(path)[0]


@lru_cache(maxsize=512)
def _node_contents(
    path: str,
    modified: int,
    size: int,
    changed: int,
    dependencies: tuple[tuple[str, int, int, int, int], ...],
    root: Optional[Union[Path, str]],
) -> dict[int, str]:
    del modified, size, changed, dependencies
    doc, binary = read_glb(path)
    unsupported = set(doc.get("extensionsRequired", ())) - {"EXT_mesh_gpu_instancing"}
    if doc.get("skins") or doc.get("animations") or unsupported:
        raise ValueError(
            "Animated, skinned or unsupported required-extension models need explicit object review"
        )

    @cache
    def buffer(index: int) -> bytes:
        value = doc["buffers"][index]
        if value.get("uri"):
            return resource_bytes(path, value["uri"], root)
        if index != 0:
            raise ValueError("Only the first buffer can use the GLB binary chunk")
        return binary

    @cache
    def view(index):
        value = doc["bufferViews"][index]
        start = value.get("byteOffset", 0)
        data = buffer(value.get("buffer", 0))[start : start + value["byteLength"]]
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
            uri = image.pop("uri", "")
            data = resource_bytes(path, uri, root)
            suffix = Path(uri).suffix
            if suffix not in IMAGE_MIMES:
                raise ValueError("External image must use a supported image resource")
            image.setdefault("mimeType", IMAGE_MIMES[suffix])
            image["bufferView"] = hashlib.sha256(data).hexdigest()
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

    def node_extensions(value):
        if not value:
            return value
        value = json.loads(json.dumps(value))
        instancing = value.get("EXT_mesh_gpu_instancing")
        if instancing and "attributes" in instancing:
            instancing["attributes"] = {
                semantic: accessor(index)
                for semantic, index in instancing["attributes"].items()
            }
        return value

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
                    "extensions": node_extensions(node.get("extensions")),
                }
            )
        for child in node.get("children", []):
            visit(child, properties, transforms)

    for index in doc["scenes"][doc.get("scene", 0)]["nodes"]:
        visit(index, {}, [])
    return result


def content_digest(root: Path, file: Union[str, Path], nodes: Iterable[int]) -> str:
    path = (root / file).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Model unavailable")
    stat = path.stat()
    contents = node_contents(
        str(path), stat.st_mtime_ns, stat.st_size, str(root.resolve())
    )
    values = sorted(contents[index] for index in nodes)
    doc = _document(str(path), stat.st_mtime_ns, stat.st_size, stat.st_ctime_ns)
    instances = doc.get("extras", {}).get("templateInstances")
    if instances:
        # Referenced materials may have no remaining host mesh. Hash their render
        # inputs too, resolving texture resources instead of container indices.
        from devtools.asset_design.shared_manifest import _Model

        model = _Model(str(path))
        semantic = json.loads(json.dumps(instances))
        for instance in semantic:
            for binding in instance["bindings"]:
                binding["materials"] = [
                    model.textures(doc["materials"][index])
                    if index is not None
                    else None
                    for index in binding.get("materials", [])
                ]
        return digest({"nodes": values, "templateInstances": semantic})
    return digest(values)
