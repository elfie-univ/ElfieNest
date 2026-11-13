"""The lake and waterfall landing sheet meet as regular coplanar surfaces."""

from collections import Counter, defaultdict

from test.godot.asset_geometry import _Model
from test.godot.estate_assets.test_pod_desktop_contacts import _triangles
from test.godot.test_courtyard_component_geometry import ROOT

IDENTITY = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
WATER_SURFACES = (
    ("lake", "COMPLETE Inset natural lake"),
    ("fountain", "COMPLETE Inset natural lake receiving under spillway"),
)


def water_faces(file, name):
    model = _Model(str(ROOT / f"courtyard/parts/waterside/{file}.glb"))
    node = next(
        i
        for i, n in enumerate(model.doc["nodes"])
        if n.get("extras", {}).get("source_name") == name
    )
    return list(_triangles(model, node, IDENTITY))


def test_main_lake_and_landing_sheet_share_one_exact_water_height():
    heights = [
        p[1]
        for file, name in WATER_SURFACES
        for tri in water_faces(file, name)
        for p in tri
    ]
    assert max(heights) - min(heights) < 1e-7
    assert abs(heights[0] + 0.39) < 1e-7


def test_both_water_sheets_have_one_regular_boundary_without_sliver_branches():
    for file, name in WATER_SURFACES:
        edges = Counter()
        for tri in water_faces(file, name):
            points = [tuple(round(v, 5) for v in p) for p in tri]
            a, b, c = points
            assert (
                abs((b[0] - a[0]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[0] - a[0]))
                > 1e-10
            )
            for p, q in zip(points, points[1:] + points[:1]):
                edges[tuple(sorted((p, q)))] += 1
        assert max(edges.values()) == 2
        graph = defaultdict(set)
        for (a, b), count in edges.items():
            if count == 1:
                graph[a].add(b)
                graph[b].add(a)
        assert graph and {len(v) for v in graph.values()} == {2}, name
        reached, pending = set(), [next(iter(graph))]
        while pending:
            point = pending.pop()
            if point not in reached:
                reached.add(point)
                pending.extend(graph[point] - reached)
        assert reached == set(graph), name
