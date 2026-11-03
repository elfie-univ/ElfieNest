"""The four worktops must fit the actual bed shell, including their head corners."""

import math
import struct
from functools import lru_cache
from pathlib import Path

import pytest

from devtools.asset_design.shared_manifest import _inverse, _Model, _multiply

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "devtools/asset_design/assets/layouts/pod_bedroom/source/model.glb"
RUNTIME = ROOT / "godot_project/rooms/estate/ElfieNest-complete-final.glb"


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
def _models():
    return _Model(str(SOURCE)), _Model(str(RUNTIME))


@pytest.mark.parametrize("resident", "ABCD")
def test_four_desktops_touch_bed_shell_in_source_and_runtime(resident):
    source, runtime = _models()
    source_bed = next(
        i
        for i, n in enumerate(source.doc["nodes"])
        if n.get("extras", {}).get("piece") == "shell"
        and n.get("extras", {}).get("resident") == resident
    )
    frame = _inverse(source.world(source_bed))
    beds = [
        i
        for i, n in enumerate(runtime.doc["nodes"])
        if n.get("extras", {}).get("module") == "M01"
        and n.get("extras", {}).get("piece") == "shell"
    ]
    bed = min(
        beds,
        key=lambda i: sum(
            abs(runtime.world(i)[r][3] - source.world(source_bed)[r][3])
            for r in range(3)
        ),
    )
    bed_triangles = list(_triangles(runtime, bed, frame))
    for model in (source, runtime):
        desk = next(
            i
            for i, n in enumerate(model.doc["nodes"])
            if n.get("extras", {}).get("module") == "M01"
            and n.get("extras", {}).get("piece") == "worktop"
            and n.get("extras", {}).get("resident") == resident
        )
        desk_triangles = list(_triangles(model, desk, frame))
        for height in (0.551, 0.575, 0.599):
            bed_section = _section(bed_triangles, height)
            desk_section = _section(desk_triangles, height)
            for degrees in (-101, -100, -90, -80, -70, -60, -56):
                angle = math.radians(degrees)
                br, dr = _radii(bed_section, angle), _radii(desk_section, angle)
                assert br and dr, (resident, height, degrees, model.path)
                gap = min(dr) - max(br)
                assert -0.007 <= gap <= 0.001, (
                    resident,
                    height,
                    degrees,
                    gap,
                    model.path,
                )
