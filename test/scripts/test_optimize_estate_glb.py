"""Lossless resource sharing must preserve appearance and collision references."""

import copy
import json
import struct
from pathlib import Path

from scripts.internal.build.optimize_estate_glb import optimize, share_resources


def test_optimizer_keeps_all_binary_chunks_byte_identical(tmp_path: Path) -> None:
    document = {"asset": {"version": "2.0"}, "images": [{"bufferView": 0}]}
    payload = json.dumps(document).encode()
    payload += b" " * (-len(payload) % 4)
    binary = struct.pack("<I4s", 8, b"BIN\x00") + b"12345678"
    encoded = (
        struct.pack("<4sII", b"glTF", 2, 20 + len(payload) + len(binary))
        + struct.pack("<I4s", len(payload), b"JSON")
        + payload
        + binary
    )
    source = tmp_path / "source.glb"
    output = tmp_path / "shared.glb"
    source.write_bytes(encoded)
    result = optimize(source, output)
    saved = output.read_bytes()
    length = struct.unpack_from("<I", saved, 12)[0]
    assert saved[20 + length :] == binary
    assert source.read_bytes() == encoded
    assert result["resources"]["images"] == [1, 1]


def test_sharing_preserves_pixels_material_variants_and_physics_meshes() -> None:
    doc = {
        "images": [
            {"name": "a", "bufferView": 0, "mimeType": "image/png"},
            {"name": "b", "bufferView": 0, "mimeType": "image/png"},
        ],
        "textures": [{"source": 0}, {"source": 1}, {"source": 1, "sampler": 0}],
        "materials": [
            {"name": "a", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}},
            {"name": "b", "pbrMetallicRoughness": {"baseColorTexture": {"index": 1}}},
            {"pbrMetallicRoughness": {"baseColorTexture": {"index": 2}}},
        ],
        "meshes": [
            {
                "name": "a",
                "primitives": [{"attributes": {"POSITION": 0}, "material": 0}],
            },
            {
                "name": "b",
                "primitives": [{"attributes": {"POSITION": 0}, "material": 1}],
            },
            {"primitives": [{"attributes": {"POSITION": 0}, "material": 2}]},
        ],
        "nodes": [{"name": "room", "mesh": 1}, {"mesh": 2}],
        "extensions": {
            "OMI_physics_shape": {"shapes": [{"type": "convex", "convex": {"mesh": 2}}]}
        },
    }
    original = copy.deepcopy(doc)
    optimized = share_resources(doc)
    assert doc == original
    assert len(optimized["images"]) == 1
    assert optimized["images"][0]["bufferView"] == 0
    assert len(optimized["textures"]) == 2  # Different samplers cannot be merged.
    assert len(optimized["materials"]) == 2
    assert len(optimized["meshes"]) == 2  # Different materials remain distinct.
    assert optimized["nodes"] == [{"name": "room", "mesh": 0}, {"mesh": 1}]
    assert (
        optimized["extensions"]["OMI_physics_shape"]["shapes"][0]["convex"]["mesh"] == 1
    )


def test_sharing_keeps_texture_transform_and_material_metadata() -> None:
    doc = {
        "images": [{"bufferView": 0}],
        "textures": [{"source": 0}, {"source": 0}],
        "materials": [
            {
                "extras": {"module": "a"},
                "normalTexture": {
                    "index": 1,
                    "scale": 0.4,
                    "extensions": {"KHR_texture_transform": {"offset": [0.1, 0.2]}},
                },
            },
            {"extras": {"module": "b"}, "normalTexture": {"index": 0}},
        ],
        "meshes": [],
        "nodes": [],
    }
    optimized = share_resources(doc)
    assert len(optimized["materials"]) == 2
    assert optimized["materials"][0]["normalTexture"]["index"] == 0
    assert optimized["materials"][0]["normalTexture"]["scale"] == 0.4
    assert (
        optimized["materials"][0]["normalTexture"]["extensions"]
        == doc["materials"][0]["normalTexture"]["extensions"]
    )
