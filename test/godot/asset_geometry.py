"""Read-only geometry inspection of the formal Godot estate in regression tests."""

import base64
import hashlib
import json
import struct
from functools import cache, lru_cache
from pathlib import Path
from typing import Any, Union, cast

JsonValue = Union[dict[str, Any], list[Any], str, int, float, bool, None]
IMAGE_MIMES = {".png": "image/png", ".jpg": "image/jpeg"}


def resource_bytes(model: Union[Path, str], uri: str) -> bytes:
    """Do not resolve dependencies into the removed design workspace."""
    raise ValueError("External GLB payloads need explicit Godot asset test support")


@lru_cache(maxsize=2)
def read_glb(path: Union[Path, str]) -> tuple[dict, bytes]:
    raw = Path(path).read_bytes()
    if len(raw) < 20:
        raise ValueError("Truncated GLB header")
    magic, version, total, length, kind = struct.unpack_from("<5I", raw)
    if (magic, version, total, kind) != (0x46546C67, 2, len(raw), 0x4E4F534A):
        raise ValueError("Invalid GLB container")
    end = 20 + length
    if end > len(raw):
        raise ValueError("Truncated GLB JSON")
    doc = json.loads(raw[20:end])
    if end == len(raw):
        return doc, b""
    if end + 8 > len(raw):
        raise ValueError("Truncated GLB binary header")
    size, kind = struct.unpack_from("<2I", raw, end)
    if kind != 0x004E4942 or end + 8 + size != len(raw):
        raise ValueError("Invalid GLB binary chunk")
    return doc, raw[end + 8 :]


def encode_glb(doc: dict, binary: bytes = b"") -> bytes:
    encoded = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode()
    encoded += b" " * (-len(encoded) % 4)
    binary += bytes(-len(binary) % 4)
    tail = struct.pack("<II", len(binary), 0x004E4942) + binary if binary else b""
    return (
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
        self.parents: dict[int, int] = {}
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
            key: {
                **cast(dict[str, Any], self.textures(item)),
                "index": self.texture(item["index"]),
            }
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
