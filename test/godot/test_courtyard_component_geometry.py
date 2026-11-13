"""Formal courtyard components own complete geometry and meet at real edges."""

import math
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

import pytest

from test.godot.asset_geometry import _Model
from test.godot.estate_assets.test_pod_desktop_contacts import _triangles, _values

ROOT = Path(__file__).resolve().parents[2] / "godot_project/nest"
IDENTITY = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]


@lru_cache
def model(name):
    directory = (
        "ground"
        if name == "shared-ground"
        else "shared"
        if name == "shore-stones"
        else "waterside"
    )
    return _Model(str(ROOT / f"courtyard/parts/{directory}/{name}.glb"))


def mesh_nodes(source):
    return {
        node["extras"]["source_name"]: i
        for i, node in enumerate(source.doc["nodes"])
        if "mesh" in node
        and node.get("extras", {}).get("ground_region")
        not in {"forest", "waterside", "meadow"}
    }


def faces(source, name):
    if name == "COMPLETE Building garden island":
        return (
            triangle
            for index, node in enumerate(source.doc["nodes"])
            if node.get("extras", {}).get("source_name", "").startswith(name)
            for triangle in _triangles(source, index, IDENTITY)
        )
    return _triangles(source, mesh_nodes(source)[name], IDENTITY)


def closed_edges(triangles):
    edges = Counter()
    directions = Counter()
    for triangle in triangles:
        keys = [tuple(round(value, 5) for value in point) for point in triangle]
        for a, b in zip(keys, keys[1:] + keys[:1]):
            edges[tuple(sorted((a, b)))] += 1
            directions[a, b] += 1
    return edges, directions


def test_rocks_and_raised_terrain_are_closed_consistently_wound_bodies():
    source = model("shore-stones")
    for name in mesh_nodes(source):
        edges, directions = closed_edges(faces(source, name))
        assert set(edges.values()) == {2}, (name, Counter(edges.values()))
        assert all(directions[a, b] == directions[b, a] == 1 for a, b in edges), name


def test_ground_and_shore_finish_form_one_closed_shell():
    source = model("shared-ground")
    triangles = [
        triangle
        for name in ("COMPLETE Building garden island", "WholeLakeRibbon")
        for triangle in faces(source, name)
    ]
    edges, directions = closed_edges(triangles)
    assert set(edges.values()) == {2}, Counter(edges.values())
    assert all(directions[a, b] == directions[b, a] == 1 for a, b in edges)


@pytest.mark.parametrize("low_z,high_z", [(27.1, 27.75), (30.0, 30.7)])
def test_channel_shoulder_surface_does_not_fold_back_under_the_land(low_z, high_z):
    folded = []
    for a, b, c in faces(model("shared-ground"), "COMPLETE Building garden island"):
        center = tuple((a[k] + b[k] + c[k]) / 3 for k in range(3))
        if not (23.95 < center[0] < 25.15 and low_z < center[2] < high_z):
            continue
        if min(a[1], b[1], c[1]) < -0.2:
            continue
        u = tuple(b[k] - a[k] for k in range(3))
        v = tuple(c[k] - a[k] for k in range(3))
        normal_y = u[2] * v[0] - u[0] * v[2]
        if normal_y < -1e-8:
            folded.append(center)
    assert not folded, folded


@pytest.mark.parametrize("z", [27.59356, 30.15356])
def test_channel_shoulder_meets_the_flat_land_without_a_raised_end_cap(z):
    points = {
        tuple(point)
        for triangle in faces(model("shared-ground"), "COMPLETE Building garden island")
        for point in triangle
        if 24.2 < point[0] < 24.64 and abs(point[2] - z) < 0.00001 and point[1] > -0.2
    }
    assert points
    assert all(abs(point[1] + 0.051) < 0.00001 for point in points), points


@pytest.mark.parametrize("x,z", [(13.0, 26.0), (17.0, 28.0), (20.0, 30.0)])
def test_fountain_sits_on_ground_instead_of_a_deep_support_panel_pit(x, z):
    assert -0.052 <= ground_height(x, z) <= -0.049


@lru_cache
def ground_cells(include_shore_finish=False, terrain_only=False):
    source = model("shared-ground")
    cells = defaultdict(list)
    for name in mesh_nodes(source):
        if terrain_only and name != "COMPLETE Building garden island":
            continue
        if name == "WholeLakeRibbon" and not include_shore_finish:
            continue  # A lamp must not hide a missing land surface in this check.
        for a, b, c in faces(source, name):
            area = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
            if abs(area) < 1e-10:
                continue
            for x in range(
                math.floor(min(a[0], b[0], c[0])), math.floor(max(a[0], b[0], c[0])) + 1
            ):
                for z in range(
                    math.floor(min(a[2], b[2], c[2])),
                    math.floor(max(a[2], b[2], c[2])) + 1,
                ):
                    cells[x, z].append((a, b, c, area))
    return cells


def heights(triangles, x, z):
    result = []
    for a, b, c, area in triangles:
        u = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / area
        v = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / area
        if min(u, v, 1 - u - v) >= -1e-5:
            result.append(u * a[1] + v * b[1] + (1 - u - v) * c[1])
    return result


def ground_height(x, z):
    return max(
        heights(ground_cells()[math.floor(x), math.floor(z)], x, z), default=-math.inf
    )


def test_forest_trail_stays_above_the_actual_terrain():
    cells = ground_cells(terrain_only=True)
    failures = []
    for triangle in faces(
        model("shared-ground"), "FOREST TRAIL smooth gravel main loop and return spur"
    ):
        a, b, c = triangle
        area = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
        if abs(area) < 1e-8:
            continue
        samples = [tuple(sum(p[k] for p in triangle) / 3 for k in range(3))]
        samples.extend(
            tuple((p[k] + q[k]) / 2 for k in range(3))
            for p, q in zip(triangle, triangle[1:] + triangle[:1])
        )
        for x, y, z in samples:
            terrain = max(
                heights(cells[math.floor(x), math.floor(z)], x, z), default=-math.inf
            )
            if y - terrain < 0.004:
                failures.append((x, z, y - terrain))
    assert not failures, failures[:8]


def surface_orientation(source, name, x, z):
    node = source.doc["nodes"][mesh_nodes(source)[name]]
    candidates = []
    for primitive in source.doc["meshes"][node["mesh"]]["primitives"]:
        points = _values(source, primitive["attributes"]["POSITION"])
        normals = _values(source, primitive["attributes"]["NORMAL"])
        indices = [row[0] for row in _values(source, primitive["indices"])]
        for at in range(0, len(indices), 3):
            a, b, c = [points[i] for i in indices[at : at + 3]]
            area = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
            if abs(area) < 1e-10:
                continue
            hits = heights([(a, b, c, area)], x, z)
            if hits:
                ny = sum(normals[i][1] for i in indices[at : at + 3])
                candidates.append((hits[0], math.copysign(1, -area * ny)))
    return max(candidates)[1]


@pytest.mark.parametrize(
    "x,z", [(23.4, 27.4), (23.4, 30.3), (23.5304, 22.9463), (23.2429, 23.7352)]
)
def test_repaired_shoulders_match_the_adjacent_soil_face_orientation(x, z):
    source = model("shared-ground")
    name = "COMPLETE Building garden island"
    assert surface_orientation(source, name, x, z) == 1
    assert surface_orientation(source, name, 23.4, 27.0) == 1


def test_lake_bank_has_one_connected_body_instead_of_overlapping_old_layers():
    source = model("shared-ground")
    assert not any(name.startswith("CY R003 corrected ") for name in mesh_nodes(source))
    assert "CY SHORE solid Continuous lawn with true lake opening" not in mesh_nodes(
        source
    )
    assert not any(name.startswith("GROUNDED soil") for name in mesh_nodes(source))
    parent = {}
    edges = Counter()

    def find(key):
        parent.setdefault(key, key)
        root = key
        while parent[root] != root:
            root = parent[root]
        while parent[key] != key:
            next_key = parent[key]
            parent[key] = root
            key = next_key
        return root

    triangles = [
        triangle
        for name in ("COMPLETE Building garden island", "WholeLakeRibbon")
        for triangle in faces(source, name)
    ]
    for tri in triangles:
        keys = [tuple(round(v, 5) for v in point) for point in tri]
        for a, b in zip(keys, keys[1:] + keys[:1]):
            edges[tuple(sorted((a, b)))] += 1
        root = find(keys[0])
        for key in keys[1:]:
            parent[find(key)] = root
    assert len({find(key) for key in parent}) == 1
    assert set(edges.values()) == {2}, (
        "The bank must be closed without open or overlapping faces"
    )


def test_open_channel_contains_no_ground_panels_or_loose_chips():
    source = model("shared-ground")
    failures = []
    for name in mesh_nodes(source):
        for triangle in faces(source, name):
            polygon = triangle
            for axis, limit, sign in [
                (0, 22.95, 1),
                (0, 25.35, -1),
                (2, 27.88, 1),
                (2, 29.86, -1),
                (1, -1.09, 1),
                (1, 0.3, -1),
            ]:
                output = []
                for a, b in zip(polygon, polygon[1:] + polygon[:1]):
                    da, db = (a[axis] - limit) * sign, (b[axis] - limit) * sign
                    if da >= 0:
                        output.append(a)
                    if (da < 0) != (db < 0):
                        t = da / (da - db)
                        output.append(tuple(a[k] + (b[k] - a[k]) * t for k in range(3)))
                polygon = output
                if len(polygon) < 3:
                    break
            for j in range(1, len(polygon) - 1):
                a, b, c = polygon[0], polygon[j], polygon[j + 1]
                u, v = [b[k] - a[k] for k in range(3)], [c[k] - a[k] for k in range(3)]
                area = sum(
                    x * x
                    for x in (
                        u[1] * v[2] - u[2] * v[1],
                        u[2] * v[0] - u[0] * v[2],
                        u[0] * v[1] - u[1] * v[0],
                    )
                )
                if area > 1e-12:
                    failures.append(name)
                    break
    assert not failures, Counter(failures)


def test_components_have_one_owner_and_no_standalone_platform():
    owners = defaultdict(list)
    for name in ("shared-ground", "lake", "fountain"):
        for node in mesh_nodes(model(name)):
            owners[node].append(name)
    assert owners["WholeLakeRibbon"] == ["shared-ground"]
    assert owners["CY R003 circular waterfront platform closed foundation"] == [
        "shared-ground"
    ]
    assert owners["ROAD REF • fountain coping bedding"] == ["fountain"]
    assert owners["ROAD REF • fountain radial limestone coping"] == ["fountain"]
    assert set(mesh_nodes(model("lake"))) == {
        "COMPLETE Inset natural lake",
        *(f"lotus_leaf_{i:02d}" for i in range(1, 112)),
        *(f"lotus_bloom_{i:02d}" for i in range(1, 11)),
        *(f"lotus_bud_{i:02d}" for i in range(1, 7)),
    }
    assert not list((ROOT / "courtyard").rglob("waterside-path.glb*"))


def test_menu_and_formal_files_are_bijective():
    import json

    index = json.loads((ROOT / "assembly/asset-index.json").read_text())
    entries = index["fileGraph"]["entries"]
    leaves = []

    def visit(items):
        for item in items:
            if "children" in item:
                visit(item["children"])
            else:
                leaves.append(item["id"])

    visit(index["fileGraph"]["categories"])
    assert Counter(leaves) == Counter(entries.keys())
    assert set(index["previews"]) == set(entries)
    assert "source:waterside-path" not in entries
    files = [entry["file"] for entry in entries.values()]
    actual = {
        str(p.relative_to(ROOT))
        for folder in (
            "furniture/layouts",
            "furniture/sets",
            "furniture/shared",
            "furniture/textures",
            "buildings",
            "courtyard",
            "assembly",
        )
        for p in (ROOT / folder).rglob("*")
        if p.suffix in {".glb", ".scn", ".tscn"}
    }
    assert Counter(files) == Counter(actual)


@lru_cache
def land_contact_edges():
    edges, directions = closed_edges(faces(model("shared-ground"), "WholeLakeRibbon"))
    # Use actual boundary edges, independently of the boolean mesh's vertex order.
    return [
        (a, b) if directions[a, b] else (b, a)
        for (a, b), count in edges.items()
        if count == 1 and all(0.016 < p[1] < 0.020 for p in (a, b))
    ]


def test_land_meets_the_entire_lake_ribbon_without_using_the_lamp_as_soil():
    edge = land_contact_edges()
    assert len(edge) > 100
    missing = []
    for a, b in edge:
        steps = max(1, math.ceil(math.dist(a, b) / 0.05))
        for j in range(steps):
            t = j / steps
            x, y, z = (a[k] + (b[k] - a[k]) * t for k in range(3))
            # Raycast just inside the land side; rounding the shared boundary
            # itself can place the ray a few micrometres on the lamp side.
            length = math.hypot(b[0] - a[0], b[2] - a[2])
            x -= (b[2] - a[2]) / length * 0.0001
            z += (b[0] - a[0]) / length * 0.0001
            if ground_height(x, z) < y - 0.002:
                missing.append((x, z))
    assert not missing, (
        f"Missing land contact at {len(missing)} shore samples: {missing[:4]}"
    )


def test_shore_finish_has_no_duplicate_physical_carrier_faces():
    triangles = [
        tuple(sorted(tuple(round(v, 5) for v in p) for p in triangle))
        for name in ("COMPLETE Building garden island", "WholeLakeRibbon")
        for triangle in faces(model("shared-ground"), name)
    ]
    assert set(Counter(triangles).values()) == {1}


@pytest.mark.parametrize("side,sign", [("north", -1), ("south", 1)])
def test_land_meets_both_outer_channel_walls(side, sign):
    wall = list(
        faces(model("fountain"), f"CY R001 spillway {side} continuous side wall")
    )
    points = [p for triangle in wall for p in triangle]
    left, right = min(p[0] for p in points), max(p[0] for p in points) - 0.11
    z = min(p[2] for p in points) if sign < 0 else max(p[2] for p in points)
    for j in range(1, 81):
        x = left + (right - left) * j / 81
        outside = z + sign * 0.006
        # The opaque curb finish now replaces the old carrier surface.
        cells = ground_cells(include_shore_finish=True)
        contact = max(heights(cells[math.floor(x), math.floor(outside)], x, outside))
        assert contact >= -0.10, (side, x, z)


def test_waterfall_bottom_remains_covered_by_receiving_water():
    water = []
    for source, name in [
        ("lake", "COMPLETE Inset natural lake"),
        ("fountain", "COMPLETE Inset natural lake receiving under spillway"),
    ]:
        for a, b, c in faces(model(source), name):
            area = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
            if abs(area) > 1e-10:
                water.append((a, b, c, area))
    curtain = list(
        faces(
            model("fountain"), "Continuous shallow waterfall from solid spillway crest"
        )
    )
    bottom = min(p[1] for tri in curtain for p in tri)
    edge = {p for tri in curtain for p in tri if abs(p[1] - bottom) < 1e-6}
    assert len(edge) >= 2
    for x, y, z in edge:
        assert any(abs(height - y) < 0.00002 for height in heights(water, x, z)), (
            x,
            y,
            z,
        )


@pytest.mark.parametrize(
    "x,z,maximum",
    [(-22.0, -13.0, 0.545), (16.5, -21.0, 0.625), (-20.0, -10.0, -0.044)],
)
def test_tree_contacts_use_the_forest_surface_without_an_added_mound(x, z, maximum):
    assert ground_height(x, z) <= maximum


def test_spatial_ground_regions_include_the_ring_plaza_and_waterfront():
    ground = model("shared-ground")
    regions = ground.doc.get("extras", {}).get("nest_ground_regions", {})
    assert set(regions) == {"building", "waterside", "meadow", "forest"}
    expected = {
        (0.0, 0.0): "building",
        (0.0, 23.0): "building",  # The flower-shaped entrance plaza.
        (35.0, 4.0): "waterside",  # The small decorated waterfront plaza.
        (17.0, 29.0): "waterside",  # The fountain and its surrounding ground.
        (0.0, 40.0): "meadow",
        (-22.0, -13.0): "forest",
        (16.5, -21.0): "forest",
    }
    for (x, z), owner in expected.items():
        if owner == "forest":
            continue
        assert any(point_in_polygon(x, z, polygon) for polygon in regions[owner])


def point_in_polygon(x, z, polygon):
    inside = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if (a[1] > z) != (b[1] > z) and x < (b[0] - a[0]) * (z - a[1]) / (
            b[1] - a[1]
        ) + a[0]:
            inside = not inside
    return inside
