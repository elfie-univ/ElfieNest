"""The whole-world comparison must preserve surfaces and multiplicity."""

import importlib.util
import json
import struct
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "compare_nest_snapshots", ROOT / "godot_project/tools/compare_nest_snapshots.py"
)
comparison = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(comparison)


def test_bedding_normal_variants_share_geometry_and_keep_room_and_bed_context():
    path = ROOT / "godot_project/nest/furniture/shared/bedroom/bed-shared.glb"
    data = path.read_bytes()
    size = struct.unpack_from("<I", data, 12)[0]
    document = json.loads(data[20 : 20 + size])
    nodes = {node["name"]: node for node in document["nodes"]}
    variants = [
        node for node in nodes.values() if "normal_variant_of" in node.get("extras", {})
    ]
    assert variants
    for node in variants:
        base = nodes[node["extras"]["normal_variant_of"]]
        before = document["meshes"][base["mesh"]]["primitives"]
        after = document["meshes"][node["mesh"]]["primitives"]
        assert len(before) == len(after)
        assert node["extras"]["review_visible"] is False
        for old, new in zip(before, after):
            assert old["indices"] == new["indices"]
            for attribute in set(old["attributes"]) - {"NORMAL", "TANGENT"}:
                assert old["attributes"][attribute] == new["attributes"][attribute]
    # One room can need different normals for two placements of the same shape.
    choices = nodes["part_00320"]["extras"]["nest_normal_variants"]["M02"]
    assert len(set(choices.values())) > 1
    placement = "Generated/CompleteEstate/CompleteFinal/A | Throw | botanical diagonal folded linen2"
    chosen = nodes[
        nodes["part_00971"]["extras"]["nest_normal_variants"]["M02"][placement]
    ]
    primitive = document["meshes"][chosen["mesh"]]["primitives"][0]
    accessor = document["accessors"][primitive["attributes"]["NORMAL"]]
    view = document["bufferViews"][accessor["bufferView"]]
    offset = 28 + size + view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    normal = struct.unpack_from(
        "<fff", data, offset + 1744 * view.get("byteStride", 12)
    )
    assert normal == (0.5226424932479858, 0.4629787802696228, -0.7158879041671753)


def test_triangle_canonicalization_preserves_winding_and_duplicate_faces():
    points = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    original = comparison.triangle_multiset(points, [0, 1, 2])
    assert original == comparison.triangle_multiset(points[::-1], [2, 1, 0])
    assert original != comparison.triangle_multiset(points, [0, 2, 1])
    assert original != comparison.triangle_multiset(points, [0, 1, 2] * 2)


def placed(path, center):
    return {"path": path, "kind": "mesh", "center": center}


def test_matching_reused_provenance_is_one_to_one_and_uses_space():
    before = [placed("room-a", [0, 0, 0]), placed("room-b", [10, 0, 0])]
    after = [placed("room-a", [10, 0, 0]), placed("room-a", [0, 0, 0])]
    pairs, missing, extra = comparison.match_placements(before, after)
    assert pairs == [(0, 1), (1, 0)]
    assert missing == extra == []


def test_duplicate_at_one_location_cannot_replace_a_missing_component():
    before = [placed("a", [0, 0, 0]), placed("b", [10, 0, 0])]
    after = [placed("a", [0, 0, 0]), placed("a", [0, 0, 0])]
    pairs, missing, extra = comparison.match_placements(before, after)
    assert len(pairs) == 1
    assert missing == [1]
    assert len(extra) == 1


def test_provenance_match_reports_large_movement_rather_than_hiding_it():
    before = [placed("a", [0, 0, 0])]
    after = [placed("a", [100, 0, 0])]
    assert comparison.match_placements(before, after)[0] == [(0, 0)]


def test_vertex_permutation_keeps_corner_attribute_correspondence():
    old = {"position": [(0, 0, 0), (1, 0, 0), (0, 1, 0)], "index": [0, 1, 2]}
    new = {"position": old["position"][::-1], "index": [2, 1, 0]}
    assert comparison.vertex_correspondence(old, new) == [2, 1, 0]
    new["index"] = [2, 0, 1]
    assert comparison.vertex_correspondence(old, new) is None


def test_surface_bound_covers_every_point_under_triangle_correspondence():
    old = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    new = [(0, 0, 0.003), (1, 0, 0), (0, 1, 0)]
    assert comparison.maximum_displacement(old, new) == pytest.approx(0.003)


def test_resource_hash_ignores_buffer_offsets_but_detects_content_changes():
    old = {"dtype": "f32", "count": 3, "bytes": 12, "offset": 0, "sha256": "one"}
    new = {**old, "offset": 500}
    assert comparison.semantic_value(old) == comparison.semantic_value(new)
    new["sha256"] = "two"
    assert comparison.semantic_value(old) != comparison.semantic_value(new)


class InlineRows(list):
    width = 3


class InlineSnapshot:
    def rows(self, description):
        rows = InlineRows(description["values"])
        rows.width = len(rows[0]) if rows and isinstance(rows[0], tuple) else 1
        return rows


def inline_surface(positions, indices, normals):
    return {
        "primitive": 3,
        "arrays": {
            key: {
                "sha256": comparison.digest(values),
                "values": values,
                "count": len(values),
            }
            for key, values in {
                "position": positions,
                "index": indices,
                "normal": normals,
            }.items()
        },
    }


def test_vertex_permutation_cannot_hide_changed_corner_normals():
    positions = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    normals = [(0, 0, 1), (0, 0, 1), (0, 1, 0)]
    old = inline_surface(positions, [0, 1, 2], normals)
    new = inline_surface(positions[::-1], [2, 1, 0], normals)
    source = InlineSnapshot()
    result = comparison.compare_surface(
        source, source, old, new, comparison.IDENTITY, comparison.IDENTITY
    )
    assert result["max_position_m"] == 0
    assert result["max_normal_degrees"] == pytest.approx(90)


def test_truncated_snapshot_array_cannot_pass():
    description = {"dtype": "v3f32", "count": 1, "offset": 0, "bytes": 12}
    with pytest.raises(ValueError, match="outside buffer"):
        comparison.Rows(b"\0" * 8, description)


def test_same_index_sequence_can_contain_reordered_vertices():
    p = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    old = inline_surface(p, [0, 1, 2], [(0, 0, 1)] * 3)
    new = inline_surface(p[1:] + p[:1], [0, 1, 2], [(0, 0, 1)] * 3)
    source = InlineSnapshot()
    result = comparison.compare_surface(
        source, source, old, new, comparison.IDENTITY, comparison.IDENTITY
    )
    assert result["max_position_m"] == 0


def test_identical_tangents_must_be_compared_in_world_space():
    p = [(0, 0, 0)] * 3
    surface = inline_surface(p, [0, 1, 2], [(0, 1, 0)] * 3)
    surface["arrays"]["tangent"] = {"sha256": "same", "values": [1, 0, 0, 1] * 3}
    rotated = (0, 0, -1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1)
    source = InlineSnapshot()
    result = comparison.compare_surface(
        source, source, surface, surface, comparison.IDENTITY, rotated
    )
    assert result["attributes"]["tangent"]["angle_degrees"] == pytest.approx(90)


def test_particle_mesh_resource_ids_are_not_geometry_identity():
    snapshots = []
    for key in ["0", "99"]:
        snapshot = comparison.Snapshot.__new__(comparison.Snapshot)
        snapshot.resources, snapshot.resolving = {}, set()
        snapshot.document = {
            "resources": {"a": {"type": "QuadMesh", "mesh": key}},
            "meshes": {key: {"surfaces": [], "blend_shapes": 0}},
        }
        snapshots.append(snapshot)
    assert snapshots[0].resolve({"resource": "a"}) == snapshots[1].resolve(
        {"resource": "a"}
    )


def test_material_texture_comparison_uses_consumed_channels_only():
    def snapshot(pixels):
        item = comparison.Snapshot.__new__(comparison.Snapshot)
        item.data = bytes(pixels)
        item.resources, item.resolving = {}, set()
        item.document = {
            "resources": {
                "texture": {
                    "type": "Texture2D",
                    "image": {
                        "width": 1,
                        "height": 1,
                        "format": 5,
                        "mipmaps": False,
                        "pixels": {
                            "dtype": "u8",
                            "offset": 0,
                            "count": 4,
                            "bytes": 4,
                            "sha256": comparison.hashlib.sha256(
                                bytes(pixels)
                            ).hexdigest(),
                        },
                    },
                },
                "material": {
                    "type": "StandardMaterial3D",
                    "properties": {"normal_texture": {"resource": "texture"}},
                },
            }
        }
        return item

    a, b = snapshot([120, 128, 254, 255]), snapshot([120, 128, 253, 255])
    assert a.resolve({"resource": "material"}) == b.resolve({"resource": "material"})
    assert a.resolve({"resource": "texture"}) != b.resolve({"resource": "texture"})
    c = snapshot([121, 128, 254, 255])
    assert a.resolve({"resource": "material"}) != c.resolve({"resource": "material"})


def test_normal_vector_length_change_remains_a_render_input_difference():
    p = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    a = inline_surface(p, [0, 1, 2], [(0, 0, 1)] * 3)
    b = inline_surface(p, [0, 1, 2], [(0, 0, 0.5)] * 3)
    result = comparison.compare_surface(
        InlineSnapshot(),
        InlineSnapshot(),
        a,
        b,
        comparison.IDENTITY,
        comparison.IDENTITY,
    )
    assert result["attributes"]["normal_length"] == pytest.approx(0.5)


def test_batch_surface_bound_accounts_for_nonuniform_instance_scale():
    local = {"position": 0.001, "normal": 0.1, "surfaces": []}
    scale = (10, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0.1, 0, 0, 0, 0, 1)
    result = comparison.batch_bound(local, [scale])
    assert result["position"] >= 0.01
    assert result["normal"] > local["normal"]


def test_batch_bound_includes_changed_parent_pose():
    before = comparison.IDENTITY
    after = (*before[:12], 0.004, 0, 0, 1)
    result = comparison.batch_bound(
        {"position": 0, "normal": 0}, [before], [after], [(0, 0, 0), (1, 1, 1)]
    )
    assert result["position"] == pytest.approx(0.004)


def test_complete_comparison_accepts_equal_world_and_rejects_an_extra_copy():
    class World(InlineSnapshot):
        path = Path("synthetic.json")

        def __init__(self):
            surface = inline_surface(
                [(0, 0, 0), (1, 0, 0), (0, 1, 0)], [0, 1, 2], [(0, 0, 1)] * 3
            )
            placement = {
                **placed("a", [0, 0, 0]),
                "mesh": "one",
                "matrix": comparison.IDENTITY,
                "file": "component.glb",
                "node": "a",
                "materials": [],
                "visible": True,
            }
            self.document = {
                "meshes": {"one": {"surfaces": [surface], "blend_shapes": 0}},
                "placements": [placement],
                "errors": [],
                "lights": [],
                "particles": [],
                "environments": [],
                "state": {},
                "engine": {},
            }

        def resolve(self, value):
            return value

    a, b = World(), World()
    assert comparison.compare(a, b)["strictly_equal"]
    b.document["placements"].append(dict(b.document["placements"][0]))
    report = comparison.compare(a, b)
    assert not report["strictly_equal"]
    assert len(report["extra"]) == 1
    b.document["placements"].pop()
    for world in (a, b):
        item = world.document["placements"][0]
        item["kind"] = "batch"
        item["batch"] = {
            "count": 1,
            "buffer": {"count": 0},
            "colors": False,
            "custom_data": False,
            "format": 1,
            "visible": -1,
        }
    report = comparison.compare(a, b)
    assert not report["strictly_equal"]
    assert report["unresolved"][0]["reason"] == "Missing or truncated instance buffer"


def test_tangent_handedness_accounts_for_mirrored_instance_basis():
    a = inline_surface([(0, 0, 0)] * 3, [0, 1, 2], [(0, 0, 1)] * 3)
    b = inline_surface([(0, 0, 0)] * 3, [0, 1, 2], [(0, 0, 1)] * 3)
    a["arrays"]["tangent"] = {"sha256": "a", "values": [1, 0, 0, 1] * 3}
    b["arrays"]["tangent"] = {"sha256": "b", "values": [-1, 0, 0, -1] * 3}
    mirror = (-1, *comparison.IDENTITY[1:])
    result = comparison.compare_surface(
        InlineSnapshot(), InlineSnapshot(), a, b, comparison.IDENTITY, mirror
    )
    assert "tangent" not in result["attributes"]


def test_large_world_origin_cannot_round_a_real_surface_difference_to_zero():
    a = inline_surface([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [0, 1, 2], [(0, 0, 1)] * 3)
    b = inline_surface(
        [(0, 0, 1e-20), (1, 0, 0), (0, 1, 0)], [0, 1, 2], [(0, 0, 1)] * 3
    )
    pose = (*comparison.IDENTITY[:14], 1e20, 1)
    result = comparison.compare_surface(
        InlineSnapshot(), InlineSnapshot(), a, b, pose, pose
    )
    assert result["max_position_m"] > 0


def test_cached_triangle_correspondence_still_measures_each_instance_pose():
    p = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    a = inline_surface(p, [0, 1, 2], [(0, 0, 1)] * 3)
    b = inline_surface(p[::-1], [2, 1, 0], [(0, 0, 1)] * 3)
    cache = {}
    comparison.compare_surface(
        InlineSnapshot(),
        InlineSnapshot(),
        a,
        b,
        comparison.IDENTITY,
        comparison.IDENTITY,
        correspondences=cache,
    )
    moved = (*comparison.IDENTITY[:12], 100, 0, 0, 1)
    result = comparison.compare_surface(
        InlineSnapshot(),
        InlineSnapshot(),
        a,
        b,
        comparison.IDENTITY,
        moved,
        correspondences=cache,
    )
    assert result["corresponding"]
    assert result["max_position_m"] == pytest.approx(100)


def test_importer_may_remove_unreferenced_vertices_without_removing_a_face():
    p = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    a = inline_surface(p + [(100, 100, 100)], [0, 1, 2], [(0, 0, 1)] * 4)
    b = inline_surface(p, [0, 1, 2], [(0, 0, 1)] * 3)
    result = comparison.compare_surface(
        InlineSnapshot(),
        InlineSnapshot(),
        a,
        b,
        comparison.IDENTITY,
        comparison.IDENTITY,
    )
    assert result["corresponding"]
    assert result["max_position_m"] == 0
    assert not result["attributes"]


def test_coincident_faces_match_their_own_corner_attributes():
    p = [(0, 0, 0), (1, 0, 0), (0, 1, 0)] * 2
    a = inline_surface(p, list(range(6)), [(0, 0, 1)] * 3 + [(0, 0, -1)] * 3)
    b = inline_surface(p, list(range(6)), [(0, 0, -1)] * 3 + [(0, 0, 1)] * 3)
    result = comparison.compare_surface(
        InlineSnapshot(),
        InlineSnapshot(),
        a,
        b,
        comparison.IDENTITY,
        comparison.IDENTITY,
    )
    assert result["max_position_m"] == 0
    assert result["max_normal_degrees"] == 0
