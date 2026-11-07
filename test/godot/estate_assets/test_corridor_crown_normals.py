"""The corridor wall cap must shade as a top face, not as the old side wall."""

import math

import pytest

from test.godot.asset_geometry import _Model
from test.godot.estate_assets.test_pod_desktop_contacts import ROOT, _values


@pytest.mark.parametrize(
    "relative",
    [
        "godot_project/nest/estate/ElfieNest-complete-final.glb",
    ],
)
def test_stair_corridor_caps_have_upward_normals(relative):
    model = _Model(str(ROOT / relative))
    caps = 0
    for node in model.doc["nodes"]:
        if (
            "mesh" not in node
            or node.get("extras", {}).get("source_name")
            != "ROOM • sculpted continuous shell"
            or node["extras"].get("module") != "M01"
        ):
            continue
        for primitive in model.doc["meshes"][node["mesh"]]["primitives"]:
            points = _values(model, primitive["attributes"]["POSITION"])
            normals = _values(model, primitive["attributes"]["NORMAL"])
            indices = [row[0] for row in _values(model, primitive["indices"])]
            for start in range(0, len(indices), 3):
                corners = indices[start : start + 3]
                triangle = [points[index] for index in corners]
                if (
                    min(point[1] for point in triangle) < 3.1
                    or max(point[2] for point in triangle) > -3.2
                ):
                    continue
                first, second, third = triangle
                edge_b = [second[axis] - first[axis] for axis in range(3)]
                edge_c = [third[axis] - first[axis] for axis in range(3)]
                cross = [
                    edge_b[1] * edge_c[2] - edge_b[2] * edge_c[1],
                    edge_b[2] * edge_c[0] - edge_b[0] * edge_c[2],
                    edge_b[0] * edge_c[1] - edge_b[1] * edge_c[0],
                ]
                area = math.sqrt(sum(value * value for value in cross))
                if area < 1e-10 or cross[1] / area < 0.999:
                    continue
                caps += 1
                assert all(normals[index][1] > 0.99 for index in corners), triangle
    assert caps > 50
