"""Potted branches enter their openings without low leaves cutting the rim."""

import struct
from pathlib import Path

from test.godot.asset_geometry import _matrix, _multiply, read_glb

MODEL = (
    Path(__file__).resolve().parents[2]
    / "godot_project/nest/furniture/shared/main/main-planters.glb"
)


def points(name):
    doc, data = read_glb(MODEL)
    node = next(
        n for n in doc["nodes"] if n.get("extras", {}).get("source_name") == name
    )
    rows = []

    def visit(part, transform):
        if "mesh" in part:
            for primitive in doc["meshes"][part["mesh"]]["primitives"]:
                accessor = doc["accessors"][primitive["attributes"]["POSITION"]]
                view = doc["bufferViews"][accessor["bufferView"]]
                start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
                for i in range(accessor["count"]):
                    point = struct.unpack_from(
                        "<3f", data, start + i * view.get("byteStride", 12)
                    ) + (1,)
                    rows.append(
                        [
                            sum(transform[r][c] * point[c] for c in range(4))
                            for r in range(3)
                        ]
                    )
        for index in part.get("children", []):
            child = doc["nodes"][index]
            visit(child, _multiply(transform, _matrix(child)))

    visit(node, _matrix({}))
    return rows


def center(rows):
    return [(min(p[k] for p in rows) + max(p[k] for p in rows)) / 2 for k in (0, 2)]


def test_coffee_leaves_clear_the_vase_rim():
    pot = points("Botanical V1 coffee ivory bud vase")
    leaf = points("Botanical V1 coffee sparse leafy stems part 1")
    assert min(p[1] for p in leaf) > max(p[1] for p in pot) + 0.005
    stems = points("Botanical V1 coffee sparse leafy stems part 0")
    low = min(p[1] for p in stems)
    root = center([p for p in stems if p[1] < low + 0.002])
    assert all(abs(a - b) < 0.005 for a, b in zip(root, center(pot)))
    assert low < max(p[1] for p in pot) - 0.01


def test_tall_vase_root_is_centered():
    pot = points("Botanical V1 tall niche ivory vase")
    stems = points("Botanical V1 tall fine leafy branch part 0")
    low = min(p[1] for p in stems)
    root = center([p for p in stems if p[1] < low + 0.004])
    assert all(abs(a - b) < 0.005 for a, b in zip(root, center(pot)))
