"""Each intact M01 loose cushion must rest against the actual sofa back."""

import math

import pytest

from test.godot.estate_assets.test_pod_desktop_contacts import ROOT, _section, _values
from test.godot.formal_asset_geometry import NamedModel as _Model


def _components(points, indices):
    parents = list(range(len(points)))

    def root(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    welded = {}
    for index, point in enumerate(points):
        key = tuple(round(value, 5) for value in point)
        if key in welded:
            parents[root(index)] = root(welded[key])
        else:
            welded[key] = index
    for start in range(0, len(indices), 3):
        first, second, third = indices[start : start + 3]
        parents[root(second)] = root(first)
        parents[root(third)] = root(first)
    groups = {}
    for index in set(indices):
        groups.setdefault(root(index), []).append(index)
    return [group for group in groups.values() if len(group) > 20]


def _back_triangles(model, primitive):
    points = _values(model, primitive["attributes"]["POSITION"])
    indices = [row[0] for row in _values(model, primitive["indices"])]
    return [
        [points[index] for index in indices[start : start + 3]]
        for start in range(0, len(indices), 3)
    ]


def _contact(points, triangles):
    center = [
        (min(point[axis] for point in points) + max(point[axis] for point in points))
        / 2
        for axis in range(3)
    ]
    nearest = None
    distance = math.inf
    for first, second in _section(triangles, center[1]):
        delta = (second[0] - first[0], second[1] - first[1])
        denominator = sum(value * value for value in delta)
        if denominator < 1e-16:
            continue
        weight = max(
            0,
            min(
                1,
                ((center[0] - first[0]) * delta[0] + (center[2] - first[1]) * delta[1])
                / denominator,
            ),
        )
        candidate = (first[0] + weight * delta[0], first[1] + weight * delta[1])
        candidate_distance = math.hypot(
            candidate[0] - center[0], candidate[1] - center[2]
        )
        if candidate_distance < distance:
            distance, nearest = candidate_distance, candidate
    assert nearest is not None
    direction = (
        (nearest[0] - center[0]) / distance,
        (nearest[1] - center[2]) / distance,
    )
    radius = max(
        (point[0] - center[0]) * direction[0] + (point[2] - center[2]) * direction[1]
        for point in points
    )
    return distance - radius, direction


@pytest.mark.parametrize(
    "relative",
    [
        "godot_project/nest/furniture/layouts/terraces/terrace-layout-01-local.glb",
    ],
)
def test_six_loose_cushions_contact_the_sofa_back(relative):
    model = _Model(str(ROOT / relative))
    node = next(
        node
        for node in model.doc["nodes"]
        if node.get("name") == "sofa_following_actual_wall" and "mesh" in node
    )
    primitives = model.doc["meshes"][node["mesh"]]["primitives"]
    triangles = _back_triangles(model, primitives[1])
    points = _values(model, primitives[2]["attributes"]["POSITION"])
    indices = [row[0] for row in _values(model, primitives[2]["indices"])]
    groups = _components(points, indices)
    assert len(groups) == 6
    for group in groups:
        cushion = [points[index] for index in group]
        gap, direction = _contact(cushion, triangles)
        assert -0.004 <= gap <= 0.004, (gap, direction)
