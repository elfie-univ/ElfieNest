"""Tail rig promotion preserves the accepted Tovren appearance and supports real FK."""

import hashlib
import json
import struct
from pathlib import Path

from test.godot.test_saevi_seated_tail_asset import emissive_pixels

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
    "POSITION": "42946fb78bb84ad5e20b3bf440e28a49dfb4f45a2fcdec34d4bd60084db6b1ce",
    "NORMAL": "2f2c1580cda123be3bbbbcc3516c1a79c25f702fefd955680b4c1cfa57ac6081",
    "TEXCOORD_0": "4f4711df9ba55bf2df9f73d642b455b1aff1b9cbfad585bab8e18c48fa64d37e",
    "body_texture": "e81e7ea48b3b20e8ed7b8f2c3b692bf368087810464fb985b5181bb22336302e",
}


def test_direct_seat_tail_rig_preserves_accepted_appearance():
    payload = (ROOT / "godot_project/characters/tovren/tovren.glb").read_bytes()
    size = struct.unpack_from("<I", payload, 12)[0]
    document = json.loads(payload[20 : 20 + size])
    binary = payload[28 + size :]
    for attribute, expected in EXPECTED.items():
        primitive = document["meshes"][0]["primitives"][0]
        if attribute == "body_texture":
            assert emissive_pixels(document, binary, primitive) == expected
            continue
        accessor = primitive["attributes"][attribute]
        view_index = document["accessors"][accessor]["bufferView"]
        view = document["bufferViews"][view_index]
        start = view.get("byteOffset", 0)
        assert (
            hashlib.sha256(binary[start : start + view["byteLength"]]).hexdigest()
            == expected
        )
    names = {node.get("name") for node in document["nodes"]}
    assert {f"Tail_{index:02d}" for index in range(1, 7)} <= names
