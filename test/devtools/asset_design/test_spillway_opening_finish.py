"""The waterfall opening contains stone and water, not footing fins or soil."""

from functools import lru_cache

import pytest

from devtools.asset_design.shared_manifest import _Model
from test.devtools.asset_design.test_pod_desktop_contacts import (
    ROOT,
    _point,
    _triangles,
    _values,
)

IDENTITY = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
BANKS = (
    "CY R003 corrected CY SHORE solid Continuous planted lake bank",
    "CY R003 corrected CY SHORE solid Lake sloping bank",
    "CY R003 corrected CY R002 continuous natural shore slope 0",
    "CY R003 corrected CY R002 continuous natural shore slope 1",
)


@lru_cache(maxsize=2)
def _model(path):
    return _Model(str(ROOT / path))


@pytest.mark.parametrize(
    "path",
    [
        "devtools/asset_design/assets/landscape/site/source/model.glb",
        "godot_project/rooms/estate/ElfieNest-complete-final.glb",
    ],
)
def test_waterfall_has_no_exposed_footing_fins_or_soil(path):
    model = _model(path)
    for side in ("north", "south"):
        name = f"CY R001 spillway receiving {side} bank footing"
        assert not any(
            node.get("name") == name and "mesh" in node for node in model.doc["nodes"]
        ), name
    # The clearance spans the actual outer faces of both stone walls and the
    # falling sheet. Test triangle samples, including edges, rather than AABBs.
    count = 0
    for i, node in enumerate(model.doc["nodes"]):
        if node.get("name") not in BANKS or "mesh" not in node:
            continue
        count += 1
        for triangle in _triangles(model, i, IDENTITY):
            for weights in (
                (1 / 3, 1 / 3, 1 / 3),
                (0.5, 0.5, 0),
                (0, 0.5, 0.5),
                (0.5, 0, 0.5),
            ):
                x, y, z = [
                    sum(p[k] * w for p, w in zip(triangle, weights)) for k in range(3)
                ]
                assert not (
                    24.781 < x < 25.799 and 27.5946 < z < 30.1526 and y > -0.39
                ), (node["name"], x, y, z)
    assert count == len(BANKS)


def _box_intersection(triangle, minimum, maximum):
    """Clip in 3D, including vertical soil faces missed by centroid tests."""
    polygon = triangle
    for axis, boundary, sign in (
        (0, minimum[0], 1),
        (0, maximum[0], -1),
        (1, minimum[1], 1),
        (1, maximum[1], -1),
        (2, minimum[2], 1),
        (2, maximum[2], -1),
    ):
        result = []
        for a, b in zip(polygon, polygon[1:] + polygon[:1]):
            da, db = (a[axis] - boundary) * sign, (b[axis] - boundary) * sign
            if da >= 0:
                result.append(a)
            if (da < 0) != (db < 0):
                t = da / (da - db)
                result.append(tuple(x + (y - x) * t for x, y in zip(a, b)))
        polygon = result
        if len(polygon) < 3:
            return False
    # A boundary-touching line does not occupy visible area.
    a = polygon[0]
    for b, c in zip(polygon[1:], polygon[2:]):
        u, v = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
        cross = (
            u[1] * v[2] - u[2] * v[1],
            u[2] * v[0] - u[0] * v[2],
            u[0] * v[1] - u[1] * v[0],
        )
        if sum(value * value for value in cross) > 1e-12:
            return True
    return False


def _opening_intersection(triangle):
    return _box_intersection(
        triangle, (24.7801, -0.3899, 27.3937), (25.4999, float("inf"), 30.3535)
    )


@pytest.mark.parametrize(
    "path",
    [
        "devtools/asset_design/assets/landscape/site/source/model.glb",
        "godot_project/rooms/estate/ElfieNest-complete-final.glb",
    ],
)
def test_waterfall_shoulders_exclude_embedded_grass_and_soil(path):
    model = _model(path)
    lake = next(
        i
        for i, n in enumerate(model.doc["nodes"])
        if n.get("name") == "COMPLETE Inset natural lake"
    )
    lake_height = max(p[1] for t in _triangles(model, lake, IDENTITY) for p in t)
    boxes = []
    for side in ("north", "south"):
        wall = next(
            i
            for i, n in enumerate(model.doc["nodes"])
            if n.get("name") == f"CY R001 spillway {side} continuous side wall"
        )
        points = [p for triangle in _triangles(model, wall, IDENTITY) for p in triangle]
        front = max(p[0] for p in points if p[1] < 0.41)
        boxes.append(
            (
                (front - 0.279, lake_height + 0.001, min(p[2] for p in points) + 0.001),
                (front - 0.001, 0.41, max(p[2] for p in points) - 0.001),
            )
        )
    selected = 0
    for index, node in enumerate(model.doc["nodes"]):
        name, extras = node.get("name", ""), node.get("extras", {})
        if "mesh" not in node or not (
            name in BANKS
            or name == "CY SHORE solid Continuous lawn with true lake opening"
            or extras.get("source_ground")
            == "CY SHORE solid Continuous lawn with true lake opening"
        ):
            continue
        for primitive in model.doc["meshes"][node["mesh"]]["primitives"]:
            material = model.doc["materials"][primitive["material"]].get("name", "")
            if not any(
                word in material.lower() for word in ("earth", "moss", "meadow")
            ):
                continue
            selected += 1
            points = [
                _point(model.world(index), p)
                for p in _values(model, primitive["attributes"]["POSITION"])
            ]
            indices = [v[0] for v in _values(model, primitive["indices"])]
            for offset in range(0, len(indices), 3):
                triangle = [points[i] for i in indices[offset : offset + 3]]
                for minimum, maximum in boxes:
                    if all(
                        max(p[k] for p in triangle) > minimum[k]
                        and min(p[k] for p in triangle) < maximum[k]
                        for k in range(3)
                    ):
                        assert not _box_intersection(triangle, minimum, maximum), (
                            name,
                            material,
                            triangle,
                        )
    assert selected


@pytest.mark.parametrize(
    "path",
    [
        "devtools/asset_design/assets/landscape/site/source/model.glb",
        "godot_project/rooms/estate/ElfieNest-complete-final.glb",
    ],
)
def test_waterfall_opening_excludes_structural_earth_faces(path):
    model = _model(path)
    selected = 0
    for index, node in enumerate(model.doc["nodes"]):
        extras = node.get("extras", {})
        name = node.get("name", "")
        if "mesh" not in node or not (
            name in BANKS
            or name == "CY SHORE solid Continuous lawn with true lake opening"
            or extras.get("source_ground")
            == "CY SHORE solid Continuous lawn with true lake opening"
        ):
            continue
        for primitive in model.doc["meshes"][node["mesh"]]["primitives"]:
            material = model.doc["materials"][primitive["material"]].get("name", "")
            if not any(
                word in material.lower() for word in ("earth", "moss", "meadow")
            ):
                continue
            selected += 1
            points = [
                _point(model.world(index), p)
                for p in _values(model, primitive["attributes"]["POSITION"])
            ]
            indices = [v[0] for v in _values(model, primitive["indices"])]
            for offset in range(0, len(indices), 3):
                triangle = [points[i] for i in indices[offset : offset + 3]]
                assert not _opening_intersection(triangle), (name, material, triangle)
    assert selected


@pytest.mark.parametrize(
    "path",
    [
        "devtools/asset_design/assets/landscape/site/source/model.glb",
        "godot_project/rooms/estate/ElfieNest-complete-final.glb",
    ],
)
def test_no_soil_remains_inside_the_full_stone_shoulder_width(path):
    """Check the wall thickness too, not only the light's outside boundary."""
    from itertools import product

    model = _model(path)
    minimum = (24.6001, -0.389, 27.5937)
    maximum = (26.9999, 0.4399, 30.1534)
    for index, node in enumerate(model.doc["nodes"]):
        name = node.get("name", "")
        if "mesh" not in node or not (
            node.get("extras", {}).get("source_ground")
            or name.startswith("CY R003 corrected")
            or name
            in (
                "CY SHORE solid Continuous lawn with true lake opening",
                "COMPLETE Building garden island",
            )
        ):
            continue
        world = model.world(index)
        bounds = []
        for primitive in model.doc["meshes"][node["mesh"]]["primitives"]:
            spec = model.doc["accessors"][primitive["attributes"]["POSITION"]]
            bounds.extend(
                _point(world, p) for p in product(*zip(spec["min"], spec["max"]))
            )
        if any(
            max(p[k] for p in bounds) <= minimum[k]
            or min(p[k] for p in bounds) >= maximum[k]
            for k in range(3)
        ):
            continue
        for triangle in _triangles(model, index, IDENTITY):
            if any(
                max(p[k] for p in triangle) <= minimum[k]
                or min(p[k] for p in triangle) >= maximum[k]
                for k in range(3)
            ):
                continue
            assert not _box_intersection(triangle, minimum, maximum), name
