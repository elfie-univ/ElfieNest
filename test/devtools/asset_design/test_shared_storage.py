"""Shared storage changes only where render payloads are stored."""

import copy

from devtools.asset_design.glb_resources import encode_glb, read_glb
from devtools.asset_design.object_content import content_digest
from test.devtools.asset_design.test_glb_resources import fixture


def test_externalize_keeps_scene_identity_and_shares_equal_mesh_payloads(tmp_path):
    from devtools.asset_design.shared_storage import externalize_glb

    original, _, _, _ = fixture(tmp_path)
    doc, binary = read_glb(original)
    doc["meshes"].append(copy.deepcopy(doc["meshes"][0]))
    doc["nodes"].append({"mesh": 1, "translation": [-3, 0, 0]})
    doc["scenes"][0]["nodes"].append(1)
    original.write_bytes(encode_glb(doc, binary))
    target = tmp_path / "layouts/reuse/source/model.glb"
    target.parent.mkdir(parents=True)
    externalize_glb(original, target, tmp_path)
    after, binary = read_glb(target)
    assert not binary
    assert len(after["buffers"]) == 1
    assert after["nodes"] == doc["nodes"]
    assert content_digest(tmp_path, original.name, [0, 1]) == content_digest(
        tmp_path, target.relative_to(tmp_path), [0, 1]
    )
    again = tmp_path / "layouts/reuse/source/second.glb"
    externalize_glb(target, again, tmp_path)
    assert again.read_bytes() == target.read_bytes()


def test_same_encoded_image_is_one_resource_across_models(tmp_path):
    from devtools.asset_design.shared_storage import externalize_glb

    original, _, _, resources = fixture(tmp_path)
    targets = [tmp_path / "one.glb", tmp_path / "two.glb"]
    for target in targets:
        externalize_glb(original, target, tmp_path)
    images = [read_glb(p)[0]["images"][0] for p in targets]
    assert images[0] == images[1]
    assert resources[1].is_file()
