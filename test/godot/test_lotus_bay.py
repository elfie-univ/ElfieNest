"""The approved lotus cluster leaves a clear band inside the shoreline lamps."""

import json
import math
from collections import Counter
from statistics import median

from test.godot.asset_geometry import _Model
from test.godot.estate_assets.test_pod_desktop_contacts import (
    _point,
    _triangles,
    _values,
)
from test.godot.test_courtyard_component_geometry import IDENTITY, ROOT
from test.godot.test_waterside_asset_consolidation import digest, render_rows

LAKE = ROOT / "courtyard/parts/waterside/lake.glb"
WATER_DIGEST = "e6dece4de4219ac565471223dd7b0104aa3e7a4975ec3cc8a51e5840d9e359d2"
# The accepted first placement's complete footprint, before making it denser.
PREVIOUS_BAY_POLYGON = (
    (33.95387, 14.42895),
    (33.95563, 14.35961),
    (33.95978, 14.29214),
    (33.96973, 14.22387),
    (33.99478, 14.15816),
    (34.03878, 14.10297),
    (37.31319, 11.43590),
    (37.39030, 11.38806),
    (37.47703, 11.36336),
    (37.56498, 11.35282),
    (37.65367, 11.34799),
    (37.74555, 11.35261),
    (39.71647, 11.77740),
    (39.82045, 11.82041),
    (39.90676, 11.89324),
    (39.96938, 11.98637),
    (40.01570, 12.08639),
    (40.05557, 12.18949),
    (40.08548, 12.30000),
    (40.36609, 13.53636),
    (40.61622, 14.73236),
    (40.63585, 14.84477),
    (40.63938, 14.95371),
    (40.63898, 15.05993),
    (40.62957, 15.16794),
    (40.59622, 15.27330),
    (39.73448, 17.95637),
    (39.08695, 19.04877),
    (39.03902, 19.12724),
    (38.96662, 19.18415),
    (38.87940, 19.21234),
    (38.79128, 19.21995),
    (38.62315, 19.22554),
    (38.53469, 19.21993),
    (34.65705, 18.24004),
    (34.59275, 18.22149),
    (34.52961, 18.19874),
    (34.46703, 18.16849),
    (34.41231, 18.12317),
    (34.37678, 18.06152),
    (34.36484, 17.99170),
)
BAY_POLYGON = (
    (30.0, 13.8),
    (31.0, 11.7),
    (33.5, 10.5),
    (37.4, 10.8),
    (40.3, 12.0),
    (40.95, 15.0),
    (39.9, 18.8),
    (38.5, 22.7),
    (36.8, 26.3),
    (34.3, 27.2),
    (32.8, 26.1),
    (32.4, 24.2),
    (32.9, 21.8),
    (33.2, 19.7),
    (32.4, 17.3),
    (30.6, 16.0),
)


def inside_polygon(point, polygon):
    x, z = point
    inside = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if (a[1] > z) != (b[1] > z) and x < (b[0] - a[0]) * (z - a[1]) / (
            b[1] - a[1]
        ) + a[0]:
            inside = not inside
    return inside


def plants(model):
    return [
        (i, node)
        for i, node in enumerate(model.doc["nodes"])
        if node.get("extras", {}).get("lotus_role")
    ]


def point_segment(point, a, b):
    dx, dz = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dz * dz
    t = (
        max(0, min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dz) / length))
        if length
        else 0
    )
    return math.hypot(point[0] - a[0] - t * dx, point[1] - a[1] - t * dz)


def test_lotus_counts_and_internal_mesh_reuse():
    model = _Model(str(LAKE))
    nodes = plants(model)
    assert Counter(n["extras"]["lotus_role"] for _, n in nodes) == {
        "leaf": 111,
        "bloom": 10,
        "bud": 6,
    }
    assert len({n["mesh"] for _, n in nodes}) == 8
    assert len([n for n in model.doc["nodes"] if "mesh" in n]) == 128


def test_entire_leaf_shapes_clear_the_actual_lamp_strip():
    model = _Model(str(LAKE))
    ground = _Model(str(ROOT / "courtyard/parts/ground/shared-ground.glb"))
    shore = next(
        i
        for i, node in enumerate(ground.doc["nodes"])
        if node.get("extras", {}).get("source_name") == "WholeLakeRibbon"
    )
    edges = set()
    for tri in _triangles(ground, shore, IDENTITY):
        row = [(p[0], p[2]) for p in tri]
        edges.update(tuple(sorted((a, b))) for a, b in zip(row, row[1:] + row[:1]))
    leaves = [(i, n) for i, n in plants(model) if n["extras"]["lotus_role"] == "leaf"]
    assert len(leaves) == 111
    for i, node in leaves:
        center = (node["translation"][0], node["translation"][2])
        assert inside_polygon(center, BAY_POLYGON), node["name"]
        points = [p for tri in _triangles(model, i, IDENTITY) for p in tri]
        radius = max(math.hypot(p[0] - center[0], p[2] - center[1]) for p in points)
        clearance = min(point_segment(center, a, b) for a, b in edges) - radius
        # A containing circle proves clearance of complete faces, not just samples.
        assert clearance >= 2.0, (node["name"], clearance)
        assert min(p[1] for p in points) >= -0.3900001
        border_distance = min(
            point_segment(center, a, b)
            for a, b in zip(BAY_POLYGON, BAY_POLYGON[1:] + BAY_POLYGON[:1])
        )
        assert border_distance - radius >= -0.00002, node["name"]


def test_flowers_rise_above_the_bank_and_water_mesh_is_unchanged():
    model = _Model(str(LAKE))
    blooms = [(i, n) for i, n in plants(model) if n["extras"]["lotus_role"] == "bloom"]
    assert len(blooms) == 10
    for i, node in blooms:
        height = max(p[1] for tri in _triangles(model, i, IDENTITY) for p in tri) + 0.39
        assert 1.20 <= height <= 1.65, (node["name"], height)
    rows = [
        r
        for r in render_rows(LAKE)
        if json.loads(r)["extras"]["source_name"] == "COMPLETE Inset natural lake"
    ]
    assert digest(rows) == WATER_DIGEST


def test_leaf_canopy_has_floating_low_and_high_leaves_with_real_stalks():
    model = _Model(str(LAKE))
    tiers = Counter()
    area = 0.0
    for i, node in plants(model):
        if node["extras"]["lotus_role"] != "leaf":
            continue
        tier = node["extras"].get("lotus_tier", "missing")
        tiers[tier] += 1
        blade = []
        stalk = []
        for primitive in model.doc["meshes"][node["mesh"]]["primitives"]:
            name = model.doc["materials"][primitive["material"]]["name"]
            points = [
                _point(model.world(i), p)
                for p in _values(model, primitive["attributes"]["POSITION"])
            ]
            indices = [v[0] for v in _values(model, primitive["indices"])]
            target = stalk if name == "Lotus green stems and calyx" else blade
            target.extend(points[j] for j in set(indices))
            if "leaf veins" not in name and target is blade:
                for at in range(0, len(indices), 3):
                    a, b, c = (points[j] for j in indices[at : at + 3])
                    area += (
                        abs(
                            (b[0] - a[0]) * (c[2] - a[2])
                            - (b[2] - a[2]) * (c[0] - a[0])
                        )
                        * 0.5
                    )
        height = median(p[1] + 0.39 for p in blade)
        low, high = {
            "floating": (0.02, 0.22),
            "low": (0.35, 0.85),
            "high": (0.75, 1.35),
        }.get(tier, (math.inf, -math.inf))
        assert low <= height <= high, (node["name"], tier, height)
        if tier != "floating":
            assert stalk and min(p[1] for p in stalk) < -0.37
            assert max(p[1] for p in stalk) >= min(p[1] for p in blade) - 0.02
    assert tiers == {"floating": 29, "low": 64, "high": 18}
    assert area >= 55.0, area


def test_lotus_occupies_the_new_left_and_lower_bay_instead_of_only_getting_denser():
    model = _Model(str(LAKE))
    leaves = [n for i, n in plants(model) if n["extras"]["lotus_role"] == "leaf"]
    assert min(n["translation"][0] for n in leaves) < 32.2
    assert max(n["translation"][2] for n in leaves) > 24.5


def test_pink_petals_are_closed_curved_volumes():
    model = _Model(str(LAKE))
    mesh = next(
        n["mesh"] for _, n in plants(model) if n["extras"]["lotus_role"] == "bloom"
    )
    layers = 0
    for primitive in model.doc["meshes"][mesh]["primitives"]:
        name = model.doc["materials"][primitive["material"]]["name"]
        if name not in (
            "Lotus outer rose petals",
            "Lotus middle blush petals",
            "Lotus inner pale pink petals",
        ):
            continue
        points = _values(model, primitive["attributes"]["POSITION"])
        indices = [v[0] for v in _values(model, primitive["indices"])]
        edges = Counter()
        for at in range(0, len(indices), 3):
            row = [tuple(round(v, 7) for v in points[j]) for j in indices[at : at + 3]]
            for a, b in zip(row, row[1:] + row[:1]):
                if a != b:
                    edges[tuple(sorted((a, b)))] += 1
        assert edges and set(edges.values()) == {2}, name
        layers += 1
    assert layers == 3


def test_stems_and_closed_flower_centers_face_outward():
    model = _Model(str(LAKE))
    meshes = {
        n["mesh"]
        for _, n in plants(model)
        if n["extras"]["lotus_role"] in ("bloom", "bud")
    }
    assert len(meshes) == 2
    for mesh in meshes:
        for primitive in model.doc["meshes"][mesh]["primitives"]:
            name = model.doc["materials"][primitive["material"]]["name"]
            points = _values(model, primitive["attributes"]["POSITION"])
            indices = [v[0] for v in _values(model, primitive["indices"])]
            if name == "Lotus green stems and calyx":
                normals = _values(model, primitive["attributes"]["NORMAL"])
                base = {i for i in indices if points[i][1] < 0.001}
                right = max(base, key=lambda i: points[i][0])
                front = max(base, key=lambda i: points[i][2])
                assert normals[right][0] > 0.4
                assert normals[front][2] > 0.4
            if name in ("Lotus seed cup", "Lotus warm yellow stamens"):
                volume = 0.0
                for at in range(0, len(indices), 3):
                    a, b, c = (points[i] for i in indices[at : at + 3])
                    volume += (
                        a[0] * (b[1] * c[2] - b[2] * c[1])
                        + a[1] * (b[2] * c[0] - b[0] * c[2])
                        + a[2] * (b[0] * c[1] - b[1] * c[0])
                    ) / 6
                assert volume > 0, name


# Existing canopy outline before infilling; expansion is not part of this pass.
DENSE_CANOPY_FOOTPRINT = (
    (30.933219, 14.628888),
    (30.943695, 14.555433),
    (30.962400, 14.484955),
    (30.985309, 14.416949),
    (31.011394, 14.350207),
    (31.042706, 14.284793),
    (31.659973, 13.267914),
    (31.704427, 13.210678),
    (31.761745, 13.166342),
    (31.827774, 13.136983),
    (37.639943, 11.472386),
    (37.711765, 11.465695),
    (37.782721, 11.473291),
    (37.850227, 11.489477),
    (37.914422, 11.508942),
    (37.977090, 11.529215),
    (38.039613, 11.551472),
    (38.101269, 11.579350),
    (39.605525, 12.264471),
    (39.665681, 12.301592),
    (39.715474, 12.351933),
    (39.752660, 12.412100),
    (39.778279, 12.477393),
    (40.106099, 13.537676),
    (40.121603, 13.611176),
    (40.127385, 13.684020),
    (40.128806, 13.754617),
    (40.134495, 14.958291),
    (40.132703, 15.031298),
    (40.121722, 15.241246),
    (40.113272, 15.314146),
    (40.093958, 15.386851),
    (39.693760, 16.759212),
    (39.668432, 16.830426),
    (36.773970, 24.538318),
    (36.740446, 24.615913),
    (36.694004, 24.688712),
    (36.632244, 24.749465),
    (36.016217, 25.250393),
    (35.958493, 25.295026),
    (35.891232, 25.323315),
    (34.687309, 25.589286),
    (34.607001, 25.598577),
    (34.527554, 25.598371),
    (34.449548, 25.593051),
    (34.371994, 25.584035),
    (34.294394, 25.569142),
    (34.218407, 25.544096),
    (34.147983, 25.505264),
    (34.087734, 25.452016),
    (34.040502, 25.387359),
    (33.185820, 23.816622),
    (33.149419, 23.747841),
    (33.121973, 23.677853),
    (33.048577, 23.474260),
    (33.027492, 23.401716),
    (31.204507, 15.935918),
    (30.936065, 14.703660),
)


def test_leaf_canopy_fills_the_existing_footprint_without_large_water_gaps():
    from PIL import Image, ImageChops, ImageDraw

    model = _Model(str(LAKE))
    scale = 18
    origin = (29, 9)
    size = (13 * scale, 20 * scale)
    target = Image.new("1", size)
    draw = ImageDraw.Draw(target)
    for x in range(size[0]):
        for z in range(size[1]):
            point = (origin[0] + x / scale, origin[1] + z / scale)
            if (
                inside_polygon(point, DENSE_CANOPY_FOOTPRINT)
                and min(
                    point_segment(point, a, b)
                    for a, b in zip(
                        DENSE_CANOPY_FOOTPRINT,
                        DENSE_CANOPY_FOOTPRINT[1:] + DENSE_CANOPY_FOOTPRINT[:1],
                    )
                )
                > 0.38
            ):
                draw.point((x, z), fill=255)
    canopy = Image.new("1", size)
    draw = ImageDraw.Draw(canopy)
    for index, node in plants(model):
        if node["extras"]["lotus_role"] != "leaf":
            continue
        for primitive in model.doc["meshes"][node["mesh"]]["primitives"]:
            material = model.doc["materials"][primitive["material"]]["name"]
            if "stems" in material or "veins" in material:
                continue
            points = [
                _point(model.world(index), p)
                for p in _values(model, primitive["attributes"]["POSITION"])
            ]
            indices = [v[0] for v in _values(model, primitive["indices"])]
            for at in range(0, len(indices), 3):
                draw.polygon(
                    [
                        (
                            round((points[i][0] - origin[0]) * scale),
                            round((points[i][2] - origin[1]) * scale),
                        )
                        for i in indices[at : at + 3]
                    ],
                    fill=255,
                )
    coverage = (
        ImageChops.logical_and(canopy, target).histogram()[255]
        / target.histogram()[255]
    )
    assert coverage >= 0.92, coverage
