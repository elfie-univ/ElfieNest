import math
from pathlib import Path

import pytest

from devtools.asset_design.shared_manifest import _Model
from test.devtools.asset_design.test_pod_desktop_contacts import (
    _point,
    _triangles,
    _values,
)

ROOT = Path(__file__).resolve().parents[3]


def _intersection_area(first, second):
    """Convex triangle intersection in the channel end-cap plane."""
    polygon = [(p[0], p[1]) for p in first]
    clip = [(p[0], p[1]) for p in second]

    def cross(a, b):
        return a[0] * b[1] - a[1] * b[0]

    def sub(a, b):
        return (a[0] - b[0], a[1] - b[1])

    orientation = cross(sub(clip[1], clip[0]), sub(clip[2], clip[0]))
    for a, b in zip(clip, clip[1:] + clip[:1]):
        if not polygon:
            return 0.0
        output = []
        edge = sub(b, a)
        for p, q in zip(polygon, polygon[1:] + polygon[:1]):
            dp = cross(edge, sub(p, a)) * orientation
            dq = cross(edge, sub(q, a)) * orientation
            if dp >= 0:
                output.append(p)
            if (dp < 0) != (dq < 0):
                t = dp / (dp - dq)
                output.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
        polygon = output
    return abs(sum(cross(a, b) for a, b in zip(polygon, polygon[1:] + polygon[:1]))) / 2


@pytest.mark.parametrize(
    "path",
    [
        "devtools/asset_design/assets/landscape/site/source/model.glb",
        "godot_project/rooms/estate/ElfieNest-complete-final.glb",
    ],
)
def test_inlet_coping_has_no_coplanar_bedding_overlap(path):
    model = _Model(str(ROOT / path))
    identity = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]

    def caps(name):
        i = next(i for i, n in enumerate(model.doc["nodes"]) if n.get("name") == name)
        return [
            t
            for t in _triangles(model, i, identity)
            if min(p[0] for p in t) > 21.8
            and max(p[0] for p in t) < 23.2
            and max(p[2] for p in t) - min(p[2] for p in t) < 0.0001
        ]

    finished_caps = caps("ROAD REF • fountain radial limestone coping") + caps(
        "CY R001 fountain load bearing basin wall"
    )
    for bedding in caps("ROAD REF • fountain coping bedding"):
        for stone in finished_caps:
            if abs(bedding[0][2] - stone[0][2]) < 0.0001:
                assert _intersection_area(bedding, stone) < 1e-8, (
                    "Coping and bedding expose overlapping coplanar caps inside the water channel"
                )


@pytest.mark.parametrize(
    "path",
    [
        "devtools/asset_design/assets/landscape/site/source/model.glb",
        "godot_project/rooms/estate/ElfieNest-complete-final.glb",
    ],
)
def test_channel_stays_shallow_and_above_its_bed(path):
    model = _Model(str(ROOT / path))
    points = {}
    for name in ("COMPLETE Short east spillway", "CY R001 spillway sealed trough bed"):
        index = next(
            i for i, node in enumerate(model.doc["nodes"]) if node.get("name") == name
        )
        node = model.doc["nodes"][index]
        points[name] = [
            _point(model.world(index), v)
            for primitive in model.doc["meshes"][node["mesh"]]["primitives"]
            for v in _values(model, primitive["attributes"]["POSITION"])
        ]
    bed = points["CY R001 spillway sealed trough bed"]
    left, right = min(p[0] for p in bed), max(p[0] for p in bed)
    left_height = max(p[1] for p in bed if abs(p[0] - left) < 0.001)
    right_height = max(p[1] for p in bed if abs(p[0] - right) < 0.001)
    for x, y, _ in points["COMPLETE Short east spillway"]:
        bed_height = left_height + (right_height - left_height) * (x - left) / (
            right - left
        )
        depth = y - bed_height
        assert 0.005 <= depth <= 0.05, f"Water depth {depth * 1000:.1f} mm at x={x:.3f}"


@pytest.mark.parametrize(
    "path",
    [
        "devtools/asset_design/assets/landscape/site/source/model.glb",
        "godot_project/rooms/estate/ElfieNest-complete-final.glb",
    ],
)
def test_waterfall_meets_both_channel_walls(path):
    model = _Model(str(ROOT / path))
    points = {}
    for name in (
        "Continuous shallow waterfall from solid spillway crest",
        "CY R001 spillway north continuous side wall",
        "CY R001 spillway south continuous side wall",
    ):
        index = next(
            i for i, node in enumerate(model.doc["nodes"]) if node.get("name") == name
        )
        node = model.doc["nodes"][index]
        points[name] = [
            _point(model.world(index), v)
            for primitive in model.doc["meshes"][node["mesh"]]["primitives"]
            for v in _values(model, primitive["attributes"]["POSITION"])
        ]
    curtain = points["Continuous shallow waterfall from solid spillway crest"]
    north = max(p[2] for p in points["CY R001 spillway north continuous side wall"])
    south = min(p[2] for p in points["CY R001 spillway south continuous side wall"])
    assert min(p[2] for p in curtain) <= north + 0.002
    assert max(p[2] for p in curtain) >= south - 0.002


@pytest.mark.parametrize(
    "path",
    [
        "devtools/asset_design/assets/landscape/site/source/model.glb",
        "godot_project/rooms/estate/ElfieNest-complete-final.glb",
    ],
)
def test_channel_walls_clear_coping_and_descend_beside_waterfall(path):
    model = _Model(str(ROOT / path))

    def points(name):
        i = next(i for i, n in enumerate(model.doc["nodes"]) if n.get("name") == name)
        return [
            _point(model.world(i), p)
            for primitive in model.doc["meshes"][model.doc["nodes"][i]["mesh"]][
                "primitives"
            ]
            for p in _values(model, primitive["attributes"]["POSITION"])
        ]

    pool = points("Reference fountain water")
    cx = (min(p[0] for p in pool) + max(p[0] for p in pool)) / 2
    cz = (min(p[2] for p in pool) + max(p[2] for p in pool)) / 2
    coping = points("ROAD REF • fountain radial limestone coping")
    radius = max(math.hypot(x - cx, z - cz) for x, _, z in coping)
    for side in ("north", "south"):
        wall = points(f"CY R001 spillway {side} continuous side wall")
        assert all(
            math.hypot(x - cx, z - cz) >= radius - 0.002 for x, y, z in wall if y > 0.53
        ), "Wall top overlaps the coping, causing flicker and exposed inlet caps"
        top = max(p[1] for p in wall)
        top_end = max(p[0] for p in wall if p[1] > top - 0.002)
        bottom_end = max(p[0] for p in wall if p[1] < 0.04)
        assert bottom_end - top_end > 0.2, (
            "Outlet must slope downstream instead of ending in a vertical board"
        )
