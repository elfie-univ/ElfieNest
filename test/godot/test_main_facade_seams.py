"""Window openings belong to the wall, without floating cover strips."""

import struct
from collections import defaultdict
from pathlib import Path

from test.godot.asset_geometry import read_glb


def test_upper_window_surrounds_are_connected_to_the_facade():
    path = (
        Path(__file__).resolve().parents[2]
        / "godot_project/nest/buildings/main/central-building.glb"
    )
    doc, binary = read_glb(path)
    node = next(
        n
        for n in doc["nodes"]
        if n.get("extras", {}).get("source_name")
        == "Central single continuous full-height envelope"
    )
    part = doc["meshes"][node["mesh"]]["primitives"][0]

    def read(index, width):
        accessor = doc["accessors"][index]
        view = doc["bufferViews"][accessor["bufferView"]]
        fmt = (
            "<"
            + {5126: "f", 5125: "I", 5123: "H", 5121: "B"}[accessor["componentType"]]
            * width
        )
        offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        stride = view.get("byteStride", struct.calcsize(fmt))
        return [
            struct.unpack_from(fmt, binary, offset + i * stride)
            for i in range(accessor["count"])
        ]

    points = read(part["attributes"]["POSITION"], 3)
    indices = [row[0] for row in read(part["indices"], 1)]
    parents = list(range(len(points)))

    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    # Sharp reveal normals split render vertices. Connectivity is geometric;
    # coincident positions still share an edge, as checked by the winding test.
    positions = {}
    for i, point in enumerate(points):
        key = tuple(round(v, 6) for v in point)
        if key in positions:
            parents[root(i)] = root(positions[key])
        else:
            positions[key] = i
    for a, b, c in zip(indices[::3], indices[1::3], indices[2::3]):
        parents[root(b)] = root(a)
        parents[root(c)] = root(a)
    groups = defaultdict(list)
    for i in set(indices):
        groups[root(i)].append(points[i])
    strips = [
        g
        for g in groups.values()
        if len(g) > 100 and min(p[1] for p in g) > 7 and max(p[1] for p in g) < 11.5
    ]
    assert not strips, (
        "Third-floor window surrounds must be part of the wall, not floating patches"
    )


def test_four_upper_apertures_follow_the_shared_frame_without_jagged_lips():
    """Exterior wall cuts stay inside the frame all around each shared opening."""
    import math

    path = (
        Path(__file__).resolve().parents[2]
        / "godot_project/nest/buildings/main/central-building.glb"
    )
    doc, binary = read_glb(path)

    def values(index, width):
        a = doc["accessors"][index]
        view = doc["bufferViews"][a["bufferView"]]
        fmt = (
            "<"
            + {5126: "f", 5125: "I", 5123: "H", 5121: "B"}[a["componentType"]] * width
        )
        offset = view.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = view.get("byteStride", struct.calcsize(fmt))
        return [
            struct.unpack_from(fmt, binary, offset + i * stride)
            for i in range(a["count"])
        ]

    def primitive(name):
        node = next(
            n for n in doc["nodes"] if n.get("extras", {}).get("source_name") == name
        )
        return doc["meshes"][node["mesh"]]["primitives"][0]

    wall = primitive("Central single continuous full-height envelope")
    points = values(wall["attributes"]["POSITION"], 3)
    normals = values(wall["attributes"]["NORMAL"], 3)
    indices = [v[0] for v in values(wall["indices"], 1)]
    exterior = [
        (p[0] * n[0] + p[2] * n[2]) / math.hypot(p[0], p[2]) > 0.45
        for p, n in zip(points, normals)
    ]
    edges = defaultdict(int)
    for tri in zip(indices[::3], indices[1::3], indices[2::3]):
        if all(exterior[i] for i in tri):
            for a, b in zip(tri, tri[1:] + tri[:1]):
                edges[tuple(sorted((a, b)))] += 1
    rim = {
        i
        for edge, count in edges.items()
        if count == 1
        for i in edge
        if 7.21 < points[i][1] < 11.25
    }
    frame = primitive("Central L3 fitted reveal quadrant 1")
    xy = sorted({(x, y) for x, y, z in values(frame["attributes"]["POSITION"], 3)})

    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def half(rows):
        result = []
        for p in rows:
            while len(result) > 1 and cross(result[-2], result[-1], p) <= 0:
                result.pop()
            result.append(p)
        return result[:-1]

    outline = half(xy) + half(xy[::-1])
    quadrants = set()
    maximum = 0.0
    for i in rim:
        x, y, z = points[i]
        q = round(math.atan2(x, z) / (math.pi / 2)) % 4
        quadrants.add(q)
        local_x = [x, -z, -x, z][q]
        distances = []
        for a, b in zip(outline, outline[1:] + outline[:1]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            t = max(
                0,
                min(1, ((local_x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy)),
            )
            distances.append(math.hypot(local_x - a[0] - t * dx, y - a[1] - t * dy))
        maximum = max(maximum, min(distances))
    assert quadrants == {0, 1, 2, 3}, "All four window apertures must be checked"
    assert maximum <= 0.030, (
        f"Window lip departs from the shared frame by {maximum:.4f} m"
    )


def test_rebuilt_upper_wall_has_closed_consistently_wound_joins():
    """Include the original lower/roof junctions, not only the opening interiors."""
    from collections import Counter

    path = (
        Path(__file__).resolve().parents[2]
        / "godot_project/nest/buildings/main/central-building.glb"
    )
    doc, binary = read_glb(path)
    node = next(
        n
        for n in doc["nodes"]
        if n.get("extras", {}).get("source_name")
        == "Central single continuous full-height envelope"
    )
    wall = doc["meshes"][node["mesh"]]["primitives"][0]

    def read(index, width):
        a = doc["accessors"][index]
        view = doc["bufferViews"][a["bufferView"]]
        fmt = (
            "<"
            + {5126: "f", 5125: "I", 5123: "H", 5121: "B"}[a["componentType"]] * width
        )
        offset = view.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = view.get("byteStride", struct.calcsize(fmt))
        return [
            struct.unpack_from(fmt, binary, offset + i * stride)
            for i in range(a["count"])
        ]

    positions = [
        tuple(round(v, 6) for v in p) for p in read(wall["attributes"]["POSITION"], 3)
    ]
    indices = [row[0] for row in read(wall["indices"], 1)]
    edges = Counter()
    for a, b, c in zip(indices[::3], indices[1::3], indices[2::3]):
        for i, j in [(a, b), (b, c), (c, a)]:
            p, q = positions[i], positions[j]
            if 6.939 < p[1] < 11.661 and 6.939 < q[1] < 11.661:
                edges[p, q] += 1
    invalid = [
        (p, q)
        for (p, q), count in edges.items()
        if p == q or count != 1 or edges[q, p] != 1
    ]
    assert not invalid, (
        f"Upper wall has {len(invalid)} open, duplicate or reversed edges"
    )
