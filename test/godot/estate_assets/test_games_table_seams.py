"""The game table's authored edge and leg caps must meet their parent solids."""

import struct
from collections import Counter
from pathlib import Path

import pytest

from test.godot.asset_geometry import read_glb, resource_bytes

ROOT = Path(__file__).resolve().parents[3]
SOURCES = [
    "godot_project/rooms/estate/ElfieNest-complete-final.glb",
]


def table_geometry(relative):
    path = ROOT / relative
    doc, embedded = read_glb(path)
    node = next(n for n in doc["nodes"] if n.get("name") == "games_central_table")
    primitives = doc["meshes"][node["mesh"]]["primitives"][:2]

    def values(index):
        accessor = doc["accessors"][index]
        view = doc["bufferViews"][accessor["bufferView"]]
        buffer = doc["buffers"][view.get("buffer", 0)]
        blob = resource_bytes(path, buffer["uri"]) if "uri" in buffer else embedded
        fmt = (
            "<3f"
            if accessor["type"] == "VEC3"
            else {5123: "<H", 5125: "<I"}[accessor["componentType"]]
        )
        size = struct.calcsize(fmt)
        start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        result = [
            struct.unpack_from(fmt, blob, start + i * view.get("byteStride", size))
            for i in range(accessor["count"])
        ]
        if accessor["type"] == "VEC3":
            assert accessor["min"] == [min(p[j] for p in result) for j in range(3)]
            assert accessor["max"] == [max(p[j] for p in result) for j in range(3)]
        return result

    points, indices = [], []
    for primitive in primitives:
        indices.extend(v[0] + len(points) for v in values(primitive["indices"]))
        points.extend(values(primitive["attributes"]["POSITION"]))
    return points, indices


@pytest.mark.parametrize("relative", SOURCES)
def test_tabletop_and_two_pedestals_have_closed_seams(relative):
    points, indices = table_geometry(relative)
    # Weld positions only for topology inspection; keep authored UV/normal seams.
    unique = {point: i for i, point in enumerate(dict.fromkeys(points))}
    triangles = [
        tuple(unique[points[j]] for j in indices[i : i + 3])
        for i in range(0, len(indices), 3)
    ]
    edges = Counter(
        tuple(sorted((triangle[i], triangle[(i + 1) % 3])))
        for triangle in triangles
        for i in range(3)
    )
    assert all(count == 2 for count in edges.values()), (
        "Detached caps leave open table edges or pedestal tops"
    )
    adjacency = {}
    for a, b in edges:
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
    seen = set()
    components = 0
    for vertex in adjacency:
        if vertex in seen:
            continue
        components += 1
        pending = [vertex]
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            pending.extend(adjacency[current] - seen)
    assert components == 4, (
        "Tabletop, chessboard base and two pedestals must each remain complete"
    )
