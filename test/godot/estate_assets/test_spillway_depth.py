import math
from pathlib import Path

import pytest

from test.godot.estate_assets.test_pod_desktop_contacts import (
    _point,
    _triangles,
    _values,
)
from test.godot.formal_asset_geometry import NamedModel as _Model

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
        "godot_project/nest/courtyard/parts/waterside/fountain.glb",
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
        "godot_project/nest/courtyard/parts/waterside/fountain.glb",
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
        "godot_project/nest/courtyard/parts/waterside/fountain.glb",
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
        "godot_project/nest/courtyard/parts/waterside/fountain.glb",
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
        assert bottom_end <= 24.881, "Lower wall must not project into the landing"
        assert top_end <= 25.0, "Preserve the existing rounded wall top"


def _front_at(triangles, y, z):
    """First face hit looking through the waterfall towards the fountain."""
    hits = []
    for a, b, c in triangles:
        determinant = (b[2] - c[2]) * (a[1] - c[1]) + (c[1] - b[1]) * (a[2] - c[2])
        if abs(determinant) < 1e-12:
            continue
        u = ((b[2] - c[2]) * (y - c[1]) + (c[1] - b[1]) * (z - c[2])) / determinant
        v = ((c[2] - a[2]) * (y - c[1]) + (a[1] - c[1]) * (z - c[2])) / determinant
        if u >= -1e-6 and v >= -1e-6 and u + v <= 1 + 1e-6:
            hits.append(u * a[0] + v * b[0] + (1 - u - v) * c[0])
    assert hits, (y, z)
    return max(hits)


@pytest.mark.parametrize(
    "path",
    [
        "godot_project/nest/courtyard/parts/waterside/fountain.glb",
    ],
)
def test_waterfall_backing_is_vertical_and_clears_the_landing(path):
    model = _Model(str(ROOT / path))
    identity = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]

    def triangles(name):
        index = next(
            i for i, node in enumerate(model.doc["nodes"]) if node.get("name") == name
        )
        return list(_triangles(model, index, identity))

    water = triangles("Continuous shallow waterfall from solid spillway crest")
    backing = triangles("CY R001 spillway supporting outlet face")
    water_z = (
        min(p[2] for t in water for p in t) + max(p[2] for t in water for p in t)
    ) * 0.5
    sides = []
    for side in ("north", "south"):
        wall = triangles(f"CY R001 spillway {side} continuous side wall")
        z = (
            min(p[2] for t in wall for p in t) + max(p[2] for t in wall for p in t)
        ) * 0.5
        sides.append((side, wall, z))
    backing_points = [p for triangle in backing for p in triangle]
    assert min(p[1] for p in backing_points) <= -0.65 + 1e-6
    assert max(p[1] for p in backing_points) >= 0.411
    assert max(p[0] for p in backing_points) <= 24.881
    front = []
    for y in (0.35, 0.2, 0.0, -0.2, -0.35, -0.6):
        stone_x = _front_at(backing, y, water_z)
        front.append(stone_x)
        for side, wall, z in sides:
            wall_x = _front_at(wall, y, z)
            assert abs(wall_x - stone_x) < 0.002, (side, y, wall_x, stone_x)
    assert max(front) - min(front) < 1e-5, "Backing must descend vertically"
    gaps = []
    for y in (0.35, 0.2, 0.0, -0.2, -0.35):
        water_x = _front_at(water, y, water_z)
        stone_x = _front_at(backing, y, water_z)
        gaps.append(water_x - stone_x)
    assert min(gaps) >= 0.025
    assert gaps[-1] > 0.45, "Leave the falling sheet and landing clear of stone"
    assert gaps == sorted(gaps)


@pytest.mark.parametrize(
    "path",
    [
        "godot_project/nest/courtyard/parts/waterside/fountain.glb",
    ],
)
def test_waterfall_backing_and_wall_fronts_do_not_overlap(path):
    model = _Model(str(ROOT / path))
    identity = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]

    def triangles(name):
        index = next(
            i for i, node in enumerate(model.doc["nodes"]) if node.get("name") == name
        )
        return list(_triangles(model, index, identity))

    backing = triangles("CY R001 spillway supporting outlet face")
    front = max(p[0] for t in backing for p in t)
    front_faces = [t for t in backing if all(abs(p[0] - front) < 1e-5 for p in t)]
    assert front_faces
    for side in ("north", "south"):
        wall = triangles(f"CY R001 spillway {side} continuous side wall")
        wall_faces = [t for t in wall if all(abs(p[0] - front) < 1e-5 for p in t)]
        assert wall_faces
        for first in front_faces:
            for second in wall_faces:
                yz_first = [(p[1], p[2], 0) for p in first]
                yz_second = [(p[1], p[2], 0) for p in second]
                assert _intersection_area(yz_first, yz_second) < 1e-8, side


@pytest.mark.parametrize(
    "path",
    [
        "godot_project/nest/courtyard/parts/waterside/fountain.glb",
    ],
)
def test_waterfall_wall_tips_have_no_downward_facing_lip(path):
    model = _Model(str(ROOT / path))
    identity = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    for side in ("north", "south"):
        index = next(
            i
            for i, node in enumerate(model.doc["nodes"])
            if node.get("name") == f"CY R001 spillway {side} continuous side wall"
        )
        triangles = list(_triangles(model, index, identity))
        front = max(p[0] for t in triangles for p in t if p[1] < 0.41)
        selected = 0
        for a, b, c in triangles:
            points = (a, b, c)
            if (
                min(p[0] for p in points) < front - 0.08
                or max(p[0] for p in points) < front - 0.01
            ):
                continue
            if min(p[1] for p in points) < 0.4119 or max(p[1] for p in points) > 0.53:
                continue
            u = [b[k] - a[k] for k in range(3)]
            v = [c[k] - a[k] for k in range(3)]
            normal = (
                u[1] * v[2] - u[2] * v[1],
                u[2] * v[0] - u[0] * v[2],
                u[0] * v[1] - u[1] * v[0],
            )
            length = math.sqrt(sum(value * value for value in normal))
            if length and normal[0] / length > 0.2:
                selected += 1
                assert normal[1] / length >= -0.04, (side, normal)
        assert selected
