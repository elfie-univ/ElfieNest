"""Identify complete static assemblies without their common scene placement.

Only matrix arithmetic roundoff is canonicalized (12 decimal places). Render
payloads remain byte-exact; these identities never rewrite model geometry.
"""

import base64
import hashlib
import json
from functools import cache, lru_cache
from pathlib import Path
from typing import Union

from devtools.asset_design.glb_resources import (
    IMAGE_MIMES,
    dependency_signature,
    read_glb,
    resource_bytes,
)

JsonValue = Union[dict, list, str, int, float, bool, None]


def _hash(value: JsonValue) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _multiply(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [
        [sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)
    ]


def _inverse(value: list[list[float]]) -> list[list[float]]:
    rows = [row[:] + [float(i == j) for j in range(4)] for i, row in enumerate(value)]
    for col in range(4):
        pivot = max(range(col, 4), key=lambda i: abs(rows[i][col]))
        rows[col], rows[pivot] = rows[pivot], rows[col]
        divisor = rows[col][col]
        if abs(divisor) < 1e-15:
            raise ValueError("Singular assembly placement")
        rows[col] = [n / divisor for n in rows[col]]
        for i in range(4):
            if i != col:
                amount = rows[i][col]
                rows[i] = [x - amount * y for x, y in zip(rows[i], rows[col])]
    return [row[4:] for row in rows]


def _matrix(node: dict) -> list[list[float]]:
    if "matrix" in node:
        return [[node["matrix"][c * 4 + r] for c in range(4)] for r in range(4)]
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    scale, translation = (
        node.get("scale", [1, 1, 1]),
        node.get("translation", [0, 0, 0]),
    )
    rows = [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]
    return [
        [rows[r][c] * scale[c] for c in range(3)] + [translation[r]] for r in range(3)
    ] + [[0, 0, 0, 1]]


class _Model:
    def __init__(self, path: str) -> None:
        self.path = path
        self.doc, self.binary = read_glb(path)
        if self.doc.get("animations") or self.doc.get("skins"):
            raise ValueError("Animated or skinned assemblies need explicit review")
        for name in ("buffer", "view", "accessor", "texture", "mesh", "world"):
            setattr(self, name, cache(getattr(self, name)))
        self.parents = {}
        for i, node in enumerate(self.doc["nodes"]):
            for child in node.get("children", []):
                if child in self.parents:
                    raise ValueError("Multiple node parents need explicit review")
                self.parents[child] = i

    def buffer(self, index: int) -> bytes:
        value = self.doc["buffers"][index]
        if "uri" in value:
            return resource_bytes(self.path, value["uri"])
        if index:
            raise ValueError("Only buffer zero can use the GLB binary chunk")
        return self.binary

    def view(self, index: int) -> bytes:
        value = self.doc["bufferViews"][index]
        start = value.get("byteOffset", 0)
        result = self.buffer(value.get("buffer", 0))[
            start : start + value["byteLength"]
        ]
        if len(result) != value["byteLength"]:
            raise ValueError("Truncated buffer view")
        return result

    def accessor(self, index: int) -> dict:
        value = self.doc["accessors"][index]
        if value.get("sparse"):
            raise ValueError("Sparse accessors need explicit review")
        component = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}[
            value["componentType"]
        ]
        shape, count = value["type"], value["count"]
        width = (
            ((int(shape[-1]) * component + 3) // 4 * 4) * int(shape[-1])
            if shape.startswith("MAT")
            else {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[shape] * component
        )
        if "bufferView" in value:
            data = self.view(value["bufferView"])
            offset = value.get("byteOffset", 0)
            stride = self.doc["bufferViews"][value["bufferView"]].get(
                "byteStride", width
            )
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
            "extensions": value.get("extensions"),
            "bytes": hashlib.sha256(packed).hexdigest(),
        }

    def texture(self, index: int) -> dict:
        value = dict(self.doc["textures"][index])
        if value.get("extensions"):
            raise ValueError("Extended texture references need explicit review")
        image = dict(self.doc["images"][value["source"]])
        image.pop("name", None)
        if "bufferView" in image:
            data = self.view(image.pop("bufferView"))
        else:
            uri = image.pop("uri")
            if uri.startswith("data:"):
                header, encoded = uri.split(",", 1)
                if not header.endswith(";base64"):
                    raise ValueError("Only base64 image data URIs are supported")
                data = base64.b64decode(encoded, validate=True)
                image.setdefault("mimeType", header[5:-7])
            else:
                data = resource_bytes(self.path, uri)
                image.setdefault("mimeType", IMAGE_MIMES[Path(uri).suffix])
        image["bytes"] = hashlib.sha256(data).hexdigest()
        value["source"] = image
        value.pop("name", None)
        if "sampler" in value:
            sampler = dict(self.doc["samplers"][value["sampler"]])
            sampler.pop("name", None)
            value["sampler"] = sampler
        return value

    def textures(self, value: JsonValue) -> JsonValue:
        if isinstance(value, list):
            return [self.textures(item) for item in value]
        if not isinstance(value, dict):
            return value
        return {
            key: {**self.textures(item), "index": self.texture(item["index"])}
            if key.endswith("Texture") and isinstance(item, dict) and "index" in item
            else self.textures(item)
            for key, item in value.items()
        }

    def mesh(self, index: int) -> str:
        value = json.loads(json.dumps(self.doc["meshes"][index]))
        value.pop("name", None)
        for primitive in value["primitives"]:
            if primitive.get("targets") or primitive.get("extensions"):
                raise ValueError(
                    "Morph targets or extended primitives need explicit review"
                )
            primitive["attributes"] = {
                key: self.accessor(item)
                for key, item in primitive["attributes"].items()
            }
            if "indices" in primitive:
                primitive["indices"] = self.accessor(primitive["indices"])
            if "material" in primitive:
                material = dict(self.doc["materials"][primitive["material"]])
                material.pop("name", None)
                primitive["material"] = self.textures(material)
        return _hash(value)

    def world(self, index: int) -> list[list[float]]:
        matrix = _matrix(self.doc["nodes"][index])
        return (
            _multiply(self.world(self.parents[index]), matrix)
            if index in self.parents
            else matrix
        )


@lru_cache(maxsize=8)
def _load(path: str, stamp: tuple[int, int, int], dependencies: tuple) -> _Model:
    del stamp, dependencies
    return _Model(path)


def _assembly(path: Path, nodes: list[int]) -> tuple[_Model, str, int]:
    path = Path(path).resolve()
    stat = path.stat()
    doc, _ = read_glb(path)
    model = _load(
        str(path),
        (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size),
        dependency_signature(path, doc),
    )
    if not nodes or len(set(nodes)) != len(nodes):
        raise ValueError("Assembly must contain distinct mesh nodes")
    meshes = {i: model.mesh(model.doc["nodes"][i]["mesh"]) for i in nodes}
    # Trying tied anchors makes repeated identical parts independent of node order.
    candidates = []
    for anchor in nodes:
        if meshes[anchor] != min(meshes.values()):
            continue
        inverse = _inverse(model.world(anchor))
        parts = []
        for i in nodes:
            node = model.doc["nodes"][i]
            relative = _multiply(inverse, model.world(i))
            parts.append(
                _hash(
                    {
                        "mesh": meshes[i],
                        "relative": [
                            round(n, 12) + 0.0 for row in relative for n in row
                        ],
                        "weights": node.get("weights"),
                        "extensions": node.get("extensions"),
                    }
                )
            )
        candidates.append((_hash(sorted(parts)), anchor))
    identity, anchor = min(candidates)
    return model, identity, anchor


def group_identity(path: Path, nodes: list[int]) -> str:
    """Hash render inputs and relative placement, ignoring names and node extras."""
    return _assembly(path, nodes)[1]


def group_summary(path: Path, nodes: list[int]) -> dict:
    """Return the chosen representative anchor and unchanged world transforms."""
    model, identity, anchor = _assembly(path, nodes)
    return {
        "identity": identity,
        "anchor": anchor,
        "anchorWorldTransform": model.world(anchor),
        "worldTransforms": [{"node": i, "matrix": model.world(i)} for i in nodes],
    }
