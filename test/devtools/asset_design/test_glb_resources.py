"""Shared render payloads retain content identity and stay inside assets."""

import hashlib
import json
import os
import struct

import pytest

from devtools.asset_design.object_content import content_digest
from devtools.asset_design.object_glb import extract_glb


def encode(doc, binary=b""):
    data = json.dumps(doc, separators=(",", ":")).encode()
    data += b" " * (-len(data) % 4)
    binary += bytes(-len(binary) % 4)
    tail = struct.pack("<II", len(binary), 0x004E4942) + binary if binary else b""
    return (
        struct.pack(
            "<5I", 0x46546C67, 2, 20 + len(data) + len(tail), len(data), 0x4E4F534A
        )
        + data
        + tail
    )


def fixture(root):
    geometry = struct.pack("<3f", 1, 2, 3)
    picture = b"example image bytes"
    doc = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "translation": [1, 2, 3], "extras": {"furniture": True}}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "material": 0}]}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "type": "VEC3", "count": 1}
        ],
        "bufferViews": [
            {"buffer": 0, "byteLength": len(geometry)},
            {"buffer": 0, "byteOffset": len(geometry), "byteLength": len(picture)},
        ],
        "buffers": [{"byteLength": len(geometry + picture)}],
        "images": [{"bufferView": 1, "mimeType": "image/png", "name": "plant"}],
        "textures": [{"source": 0}],
        "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
    }
    original = root / "original.glb"
    original.write_bytes(encode(doc, geometry + picture))
    resource_dir = root / "furniture/shared_resources/source/resources"
    resource_dir.mkdir(parents=True)
    resources = []
    for data, suffix in ((geometry, "bin"), (picture, "png")):
        path = resource_dir / (hashlib.sha256(data).hexdigest() + "." + suffix)
        path.write_bytes(data)
        resources.append(path)
    model = root / "layouts/example/source/model.glb"
    model.parent.mkdir(parents=True)
    doc["buffers"] = [
        {
            "byteLength": len(geometry),
            "uri": os.path.relpath(resources[0], model.parent),
        }
    ]
    doc["images"][0].pop("bufferView")
    doc["images"][0]["uri"] = os.path.relpath(resources[1], model.parent)
    doc["bufferViews"].pop()
    model.write_bytes(encode(doc))
    return original, model, doc, resources


def test_shared_geometry_and_image_keep_content_digest(tmp_path):
    original, model, _, _ = fixture(tmp_path)
    assert content_digest(tmp_path, model.relative_to(tmp_path), [0]) == content_digest(
        tmp_path, original.name, [0]
    )


def test_extract_shared_payloads_as_standalone_glb(tmp_path):
    original, model, _, resources = fixture(tmp_path)
    result, mapping = extract_glb(model, [0])
    target = tmp_path / "standalone.glb"
    target.write_bytes(result)
    assert mapping == {0: 0}
    expected = content_digest(tmp_path, original.name, [0])
    for path in resources:
        path.unlink()
    assert content_digest(tmp_path, target.name, [0]) == expected
    length = struct.unpack_from("<I", result, 12)[0]
    doc = json.loads(result[20 : 20 + length])
    assert "uri" not in doc["images"][0]


def test_relocate_shared_payloads_for_published_model(tmp_path):
    from devtools.asset_design.glb_resources import relocate_glb

    original, model, _, _ = fixture(tmp_path)
    target = tmp_path / "layouts/example/versions/v001/model.glb"
    target.parent.mkdir(parents=True)
    target.write_bytes(relocate_glb(model, target, root=tmp_path))
    assert content_digest(
        tmp_path, target.relative_to(tmp_path), [0]
    ) == content_digest(tmp_path, original.name, [0])


def test_mixed_embedded_and_external_buffers_keep_selected_render_data(tmp_path):
    original, model, doc, resources = fixture(tmp_path)
    geometry = resources[0].read_bytes()
    doc["buffers"].insert(0, {"byteLength": len(geometry)})
    doc["bufferViews"][0]["buffer"] = 1
    model.write_bytes(encode(doc, geometry))
    expected = content_digest(tmp_path, original.name, [0])
    assert content_digest(tmp_path, model.relative_to(tmp_path), [0]) == expected
    target = tmp_path / "mixed-extraction.glb"
    target.write_bytes(extract_glb(model, [0])[0])
    assert content_digest(tmp_path, target.name, [0]) == expected


@pytest.mark.parametrize("resource_index", [0, 1])
def test_changed_dependency_invalidates_cached_content_digest(tmp_path, resource_index):
    _, model, _, resources = fixture(tmp_path)
    content_digest(tmp_path, model.relative_to(tmp_path), [0])
    resource = resources[resource_index]
    stat = resource.stat()
    resource.write_bytes(b"x" * stat.st_size)
    os.utime(resource, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    with pytest.raises(ValueError, match="SHA256"):
        content_digest(tmp_path, model.relative_to(tmp_path), [0])


@pytest.mark.parametrize(
    "uri",
    [
        "https://example.com/image.png",
        "../../../../outside.png",
        "../../../furniture/shared_resources/source/resources/plain.png",
    ],
)
def test_unapproved_external_paths_are_rejected(tmp_path, uri):
    _, model, doc, _ = fixture(tmp_path)
    doc["images"][0]["uri"] = uri
    model.write_bytes(encode(doc))
    with pytest.raises(ValueError):
        content_digest(tmp_path, model.relative_to(tmp_path), [0])
    with pytest.raises(ValueError):
        extract_glb(model, [0])


def test_external_resource_symlink_cannot_escape_assets(tmp_path):
    root = tmp_path / "assets"
    root.mkdir()
    _, model, _, resources = fixture(root)
    outside = tmp_path / "outside.png"
    resources[1].replace(outside)
    resources[1].symlink_to(outside)
    with pytest.raises(ValueError):
        content_digest(root, model.relative_to(root), [0])
