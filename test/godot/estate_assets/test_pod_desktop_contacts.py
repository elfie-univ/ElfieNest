"""Freeze the accepted shared bed and the four worktop prototypes."""

import hashlib
import math
import struct
from functools import lru_cache
from pathlib import Path

import pytest

from test.godot.asset_geometry import _multiply
from test.godot.formal_asset_geometry import NamedModel, assert_approved_source

ROOT = Path(__file__).resolve().parents[3]
PROTOTYPE = ROOT / "godot_project/nest/furniture/shared/bedroom/bedroom-cabinet.glb"


def _values(model, accessor):
    spec = model.doc["accessors"][accessor]
    view = model.doc["bufferViews"][spec["bufferView"]]
    data = model.view(spec["bufferView"])
    width = 3 if spec["type"] == "VEC3" else 1
    component = {5121: "B", 5123: "H", 5125: "I", 5126: "f"}[spec["componentType"]]
    fmt = "<" + component * width
    stride = view.get("byteStride", struct.calcsize(fmt))
    return [
        struct.unpack_from(fmt, data, spec.get("byteOffset", 0) + i * stride)
        for i in range(spec["count"])
    ]


def _point(matrix, point):
    return tuple(
        sum(matrix[r][c] * point[c] for c in range(3)) + matrix[r][3] for r in range(3)
    )


def _triangles(model, index, frame):
    matrix = _multiply(frame, model.world(index))
    for primitive in model.doc["meshes"][model.doc["nodes"][index]["mesh"]][
        "primitives"
    ]:
        points = [
            _point(matrix, p)
            for p in _values(model, primitive["attributes"]["POSITION"])
        ]
        indices = (
            [v[0] for v in _values(model, primitive["indices"])]
            if "indices" in primitive
            else list(range(len(points)))
        )
        for start in range(0, len(indices), 3):
            yield [points[i] for i in indices[start : start + 3]]


def _section(triangles, height):
    segments = []
    for triangle in triangles:
        hits = []
        for a, b in zip(triangle, triangle[1:] + triangle[:1]):
            if (a[1] - height) * (b[1] - height) < 0:
                t = (height - a[1]) / (b[1] - a[1])
                hits.append((a[0] + t * (b[0] - a[0]), a[2] + t * (b[2] - a[2])))
        if len(hits) == 2:
            segments.append(hits)
    return segments


def _radii(segments, angle):
    x, z = math.cos(angle), math.sin(angle)
    hits = []
    for a, b in segments:
        dx, dz = b[0] - a[0], b[1] - a[1]
        determinant = x * dz - z * dx
        if abs(determinant) < 1e-10:
            continue
        radius = (a[0] * dz - a[1] * dx) / determinant
        t = (a[0] * z - a[1] * x) / determinant
        if radius > 0 and -1e-6 <= t <= 1 + 1e-6:
            hits.append(radius)
    return hits


@lru_cache
def _model():
    return NamedModel(str(PROTOTYPE))


@pytest.mark.parametrize("resident", "ABCD")
def test_four_desktop_prototypes_keep_the_approved_source_geometry(resident):
    # The accepted shared shell differs from the old merged shell. Freeze both
    # current inputs; native measures their 32 actual scene contacts/identities.
    assert_approved_source("furniture/shared/bedroom/bed-shared.glb")
    assert hashlib.sha256(PROTOTYPE.read_bytes()).hexdigest() == (
        "b9d4274561da88adcca2dc4bdfb230bbcacf03aea9aa9f5de0bde6e4ea6f4773"
    )
    model = _model()
    nodes = [
        n
        for n in model.doc["nodes"]
        if n.get("extras", {}).get("piece") == "worktop"
        and n["extras"].get("resident") == resident
    ]
    assert len(nodes) == 1
    node = nodes[0]
    assert (
        node["name"]
        == f"{resident} | longer curved desktop with compact rounded head joint"
    )
    assert node["extras"]["module"] == "M01"
    assert model.doc["meshes"][node["mesh"]]["primitives"]
