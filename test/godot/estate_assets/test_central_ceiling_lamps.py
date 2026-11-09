"""The three central lamps have the same continuous luminous face."""

import struct
from pathlib import Path

import pytest

from test.godot.asset_geometry import resource_bytes
from test.godot.formal_asset_geometry import read_glb


@pytest.mark.parametrize(
    "model",
    [
        "godot_project/nest/buildings/main/central-building.glb",
    ],
)
def test_central_lamps_have_matching_solid_diffusers(model):
    root = Path(__file__).resolve().parents[3]
    doc, binary = read_glb(root / model)
    nodes = {node.get("name"): node for node in doc["nodes"]}
    faces = []
    bodies = []
    for floor in (1, 2, 3):
        node = nodes[f"Working L{floor} circular opal ceiling diffuser"]
        mesh = doc["meshes"][node["mesh"]]
        primitive = mesh["primitives"][0]
        accessor = doc["accessors"][primitive["attributes"]["POSITION"]]
        view = doc["bufferViews"][accessor["bufferView"]]
        source = doc["buffers"][view["buffer"]]
        payload = (
            resource_bytes(root / model, source["uri"]) if "uri" in source else binary
        )
        offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        vertices = [
            struct.unpack_from("<3f", payload, offset + i * view.get("byteStride", 12))
            for i in range(accessor["count"])
        ]
        indices_accessor = doc["accessors"][primitive["indices"]]
        indices_view = doc["bufferViews"][indices_accessor["bufferView"]]
        indices_source = doc["buffers"][indices_view["buffer"]]
        indices_payload = (
            resource_bytes(root / model, indices_source["uri"])
            if "uri" in indices_source
            else binary
        )
        indices_format = {5121: "B", 5123: "H", 5125: "I"}[
            indices_accessor["componentType"]
        ]
        indices_start = indices_view.get("byteOffset", 0) + indices_accessor.get(
            "byteOffset", 0
        )
        indices = struct.unpack_from(
            "<" + indices_format * indices_accessor["count"],
            indices_payload,
            indices_start,
        )

        def covers_center(triangle, vertices=vertices):
            a, b, c = [(vertices[index][0], vertices[index][2]) for index in triangle]

            def side(p, q):
                return p[0] * q[1] - p[1] * q[0]

            signs = [side(a, b), side(b, c), side(c, a)]
            return min(signs) >= -1e-10 or max(signs) <= 1e-10

        assert any(
            covers_center(indices[i : i + 3]) for i in range(0, len(indices), 3)
        ), (
            f"Floor {floor}: luminous face must cover the center, not leave a dark recess"
        )
        material = doc["materials"][primitive["material"]]
        assert max(material.get("emissiveFactor", [0])) > 0
        faces.append(mesh)
        body = nodes[f"Working L{floor} shared thin circular ceiling body"]
        bodies.append(doc["meshes"][body["mesh"]])
    assert faces[0] == faces[1] == faces[2]
    assert bodies[0] == bodies[1] == bodies[2]
