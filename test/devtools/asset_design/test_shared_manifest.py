"""Movable assemblies share identity only when complete render inputs agree."""

import copy
import math
import struct

import pytest

from devtools.asset_design.glb_resources import encode_glb
from devtools.asset_design.shared_manifest import group_identity, group_summary


def model(tmp_path, name="model", change=None):
    positions = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    indices = struct.pack("<3H", 0, 1, 2)
    image = b"encoded-image"
    doc = {
        "asset": {"version": "2.0"},
        "scenes": [{"nodes": [2]}],
        "nodes": [
            {"mesh": 0},
            {"mesh": 0, "translation": [2, 0, 0]},
            {"children": [0, 1]},
        ],
        "meshes": [
            {
                "primitives": [
                    {"attributes": {"POSITION": 0}, "indices": 1, "material": 0}
                ]
            }
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "type": "VEC3", "count": 3},
            {"bufferView": 1, "componentType": 5123, "type": "SCALAR", "count": 3},
        ],
        "bufferViews": [
            {"buffer": 0, "byteLength": 36},
            {"buffer": 0, "byteOffset": 36, "byteLength": 6},
            {"buffer": 0, "byteOffset": 42, "byteLength": len(image)},
        ],
        "buffers": [{"byteLength": 42 + len(image)}],
        "images": [{"bufferView": 2, "mimeType": "image/png"}],
        "textures": [{"source": 0, "sampler": 0}],
        "samplers": [{"wrapS": 10497}],
        "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
    }
    payload = positions + indices + image
    if change:
        payload = change(doc, payload) or payload
    path = tmp_path / (name + ".glb")
    path.write_bytes(encode_glb(doc, payload))
    return path


def test_assembly_placement_and_selection_order_do_not_change_identity(tmp_path):
    original = model(tmp_path)

    def placed(doc, _):
        doc["nodes"][2].update(
            translation=[12, -4, 3], rotation=[0, 0, math.sin(0.4), math.cos(0.4)]
        )
        doc["nodes"][0].update(name="renamed", extras={"floor": 2})
        doc["materials"][0]["name"] = "renamed material"

    moved = model(tmp_path, "moved", placed)
    assert group_identity(original, [0, 1]) == group_identity(moved, [1, 0])
    summary = group_summary(moved, [1, 0])
    assert summary["identity"] == group_identity(original, [0, 1])
    assert len(summary["worldTransforms"]) == 2


@pytest.mark.parametrize(
    "kind", ["relative", "material", "sampler", "texture", "topology", "extension"]
)
def test_changed_render_or_relative_inputs_do_not_merge(tmp_path, kind):
    original = model(tmp_path)

    def changed(doc, payload):
        if kind == "relative":
            doc["nodes"][1]["translation"][0] += 0.01
        elif kind == "material":
            doc["materials"][0]["doubleSided"] = True
        elif kind == "sampler":
            doc["samplers"][0]["wrapS"] = 33071
        elif kind == "extension":
            doc["materials"][0]["extensions"] = {"KHR_materials_unlit": {}}
        elif kind == "texture":
            return payload[:-1] + b"!"
        elif kind == "topology":
            return payload[:36] + struct.pack("<3H", 2, 1, 0) + payload[42:]

    assert group_identity(original, [0, 1]) != group_identity(
        model(tmp_path, kind, changed), [0, 1]
    )


def test_single_node_scale_is_a_placement_property(tmp_path):
    original = model(tmp_path)
    scaled = model(
        tmp_path, "scaled", lambda d, _: d["nodes"][0].update(scale=[2, 3, 4])
    )
    assert group_identity(original, [0]) == group_identity(scaled, [0])


def test_accessor_stride_and_internal_indices_are_storage_details(tmp_path):
    original = model(tmp_path)

    def reordered(doc, payload):
        # Three interleaved positions; indices and image move together.
        interleaved = b"".join(payload[n : n + 12] + b"pad!" for n in range(0, 36, 12))
        doc["bufferViews"][0].update(byteStride=16, byteLength=48)
        for view in doc["bufferViews"][1:]:
            view["byteOffset"] += 12
        doc["buffers"][0]["byteLength"] += 12
        doc["accessors"].reverse()
        primitive = doc["meshes"][0]["primitives"][0]
        primitive.update(attributes={"POSITION": 1}, indices=0)
        doc["materials"].insert(0, copy.deepcopy(doc["materials"][0]))
        primitive["material"] = 1
        return interleaved + payload[36:]

    assert group_identity(original, [0, 1]) == group_identity(
        model(tmp_path, "reordered", reordered), [0, 1]
    )
