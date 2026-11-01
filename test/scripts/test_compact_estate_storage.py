"""Reachability includes collision meshes, and byte sharing retains stride."""

import pytest

from scripts.internal.build.compact_estate_storage import compact_storage


def test_pruning_preserves_collision_only_mesh_and_image_payload() -> None:
    doc = {
        "buffers": [{"byteLength": 20}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": i * 4, "byteLength": 4} for i in range(5)
        ],
        "accessors": [{"bufferView": i} for i in range(4)],
        "images": [{"bufferView": 4}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": i}}]} for i in range(4)],
        "nodes": [{"mesh": 2, "extras": {"source_mesh": 1}}],
        "extensions": {"OMI_physics_shape": {"shapes": [{"convex": {"mesh": 3}}]}},
    }
    doc["bufferViews"][3]["byteStride"] = 12
    output, binary, report = compact_storage(doc, b"deadgoneLIVELIVEimg!")
    assert binary == b"LIVEimg!"
    assert report["removed_meshes"] == 2
    assert output["nodes"] == [{"mesh": 0, "extras": {"source_mesh": 1}}]
    assert output["extensions"]["OMI_physics_shape"]["shapes"][0]["convex"]["mesh"] == 1
    assert output["bufferViews"][1]["byteStride"] == 12
    assert len(output["bufferViews"]) == 3
    assert doc["nodes"][0]["mesh"] == 2
    assert doc["bufferViews"][3]["byteOffset"] == 12


def test_unknown_extensions_rejected_before_pruning() -> None:
    with pytest.raises(ValueError, match="Unknown extension"):
        compact_storage({"extensionsUsed": ["EXT_unknown_references"]}, b"")
