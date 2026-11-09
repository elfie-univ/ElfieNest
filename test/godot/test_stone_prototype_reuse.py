"""The stone library stores representative shapes, not one mesh per placement."""

import hashlib
import json

from test.godot.estate_assets.test_pod_desktop_contacts import _triangles
from test.godot.test_courtyard_component_geometry import ROOT, model


def shape_key(source, node):
    return json.dumps(
        [
            {
                "attributes": {
                    key: source.accessor(value)
                    for key, value in primitive["attributes"].items()
                },
                "indices": source.accessor(primitive["indices"]),
            }
            for primitive in source.doc["meshes"][node["mesh"]]["primitives"]
        ],
        sort_keys=True,
    )


def test_round_stones_share_one_shape_with_three_material_colors():
    source = model("shore-stones")
    nodes = [
        node
        for node in source.doc["nodes"]
        if node.get("extras", {}).get("stone_family") == "pebble"
    ]
    assert (
        len(nodes) == 6
    )  # Original source names remain usable for color/size variants.
    assert len({shape_key(source, node) for node in nodes}) == 1
    colors = {
        tuple(
            source.doc["materials"][primitive["material"]]["pbrMetallicRoughness"][
                "baseColorFactor"
            ]
        )
        for node in nodes
        for primitive in source.doc["meshes"][node["mesh"]]["primitives"]
    }
    assert len(colors) == 3


def test_library_groups_four_families_in_rows_and_sorts_by_actual_size():
    source = model("shore-stones")
    identity = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    families = {key: [] for key in ("pebble", "block", "slab", "cut")}
    for index, node in enumerate(source.doc["nodes"]):
        if "mesh" not in node or not node.get("extras", {}).get("review_visible", True):
            continue
        points = [
            p for triangle in _triangles(source, index, identity) for p in triangle
        ]
        low = [min(p[axis] for p in points) for axis in range(3)]
        high = [max(p[axis] for p in points) for axis in range(3)]
        families[node["extras"]["stone_family"]].append((low, high))
    assert {key: len(rows) for key, rows in families.items()} == {
        "pebble": 1,
        "block": 9,
        "slab": 2,
        "cut": 2,
    }
    previous_back = None
    for rows in families.values():
        rows.sort(key=lambda row: row[0][0])
        assert max(row[0][2] for row in rows) - min(row[0][2] for row in rows) < 1e-5
        front = min(row[0][2] for row in rows)
        assert previous_back is None or front > previous_back
        previous_back = max(row[1][2] for row in rows)
        sizes = [max(high[a] - low[a] for a in range(3)) for low, high in rows]
        assert all(a <= b + 1e-5 for a, b in zip(sizes, sizes[1:]))


def test_distinct_block_slab_and_cut_geometry_and_materials_are_unchanged():
    source = model("shore-stones")
    rows = sorted(
        (node["name"], source.mesh(node["mesh"]))
        for node in source.doc["nodes"]
        if "mesh" in node and node["extras"]["stone_family"] != "pebble"
    )
    digest = hashlib.sha256(
        json.dumps(rows, separators=(",", ":")).encode()
    ).hexdigest()
    assert digest == "1f4f7cfcc2d2c4848b0bb2c6faf1cae0a94eef1ee397adadfac6c935fb346291"


def test_stones_have_four_families_and_fewer_shapes_than_placements():
    source = model("shore-stones")
    nodes = [node for node in source.doc["nodes"] if "mesh" in node]
    assert len({node["mesh"] for node in nodes}) < 40
    assert {node.get("extras", {}).get("stone_family") for node in nodes} == {
        "pebble",
        "block",
        "slab",
        "cut",
    }


def test_library_preview_lists_each_representative_once():
    source = model("shore-stones")
    visible = [
        node
        for node in source.doc["nodes"]
        if "mesh" in node and node.get("extras", {}).get("review_visible", True)
    ]
    paths = {node["extras"]["v044_path"] for node in visible}
    index = json.loads((ROOT / "assembly/asset-index.json").read_text())
    entry = index["fileGraph"]["entries"]["source:shore-stones"]
    assert set(entry["focus"]) == paths
    groups = index["previews"]["source:shore-stones"]["groups"]
    assert groups == []  # The GLB carries the four sorted display rows.
    assert len(paths) == len({shape_key(source, node) for node in visible}) == 14
    assert {part["id"] for part in entry["components"]} == {
        "pebble",
        "block",
        "slab",
        "cut",
    }
