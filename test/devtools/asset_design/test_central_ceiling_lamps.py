"""The three central lamps have the same continuous luminous face."""

import struct
from pathlib import Path

import pytest

from devtools.asset_design.glb_resources import read_glb, resource_bytes


@pytest.mark.parametrize(
    "model",
    [
        "devtools/asset_design/assets/buildings/central/source/model.glb",
        "godot_project/rooms/estate/ElfieNest-complete-final.glb",
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
        assert any(abs(x) < 1e-6 and abs(z) < 1e-6 for x, _, z in vertices), (
            f"Floor {floor}: luminous face must cover the center, not leave a dark recess"
        )
        material = doc["materials"][primitive["material"]]
        assert max(material.get("emissiveFactor", [0])) > 0
        faces.append(mesh)
        body = nodes[f"Working L{floor} shared thin circular ceiling body"]
        bodies.append(doc["meshes"][body["mesh"]])
    assert faces[0] == faces[1] == faces[2]
    assert bodies[0] == bodies[1] == bodies[2]
