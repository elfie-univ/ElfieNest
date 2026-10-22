"""Unchanged previews reuse validation while direct file edits remain visible."""

from devtools.asset_design.design_catalog import inventory
from devtools.asset_design.object_assets import split_assets
from test.devtools.asset_design.test_design import setup


def test_unchanged_inventory_skips_content_revalidation_and_returns_independent_values(
    tmp_path, monkeypatch
):
    from devtools.asset_design import object_registry

    setup(tmp_path)
    split_assets(tmp_path)
    first = inventory(tmp_path)
    original = object_registry.content_digest
    calls = []

    def content(*args):
        calls.append(args[1])
        return original(*args)

    monkeypatch.setattr(object_registry, "content_digest", content)
    second = inventory(tmp_path)
    assert second == first
    assert not calls
    second["objects"].clear()
    assert inventory(tmp_path) == first


def test_same_size_source_edit_invalidates_inventory(tmp_path):
    import json

    from devtools.asset_design.glb_resources import encode_glb, read_glb

    setup(tmp_path)
    split_assets(tmp_path)
    source = tmp_path / "buildings/pod/source/model.glb"
    build = source.with_name("build.json")
    data = json.loads(build.read_text())
    data["workingDraft"] = True
    build.write_text(json.dumps(data))
    doc, binary = read_glb(source)
    doc["nodes"][0]["translation"] = [3, 0, 0]
    source.write_bytes(encode_glb(doc, binary))
    first = inventory(tmp_path)
    before_size = source.stat().st_size
    doc["nodes"][0]["translation"] = [4, 0, 0]
    source.write_bytes(encode_glb(doc, binary))
    assert source.stat().st_size == before_size
    second = inventory(tmp_path)

    def draft(data):
        return next(o for o in data["objects"] if o["id"] == "building:pod")[
            "versions"
        ][0]

    assert draft(first)["draft"] and draft(second)["draft"]
    assert draft(first)["contentDigest"] != draft(second)["contentDigest"]


def test_cached_inventory_rejects_same_size_shared_resource_tampering(tmp_path):
    from devtools.asset_design.catalog_store import save_catalog
    from devtools.asset_design.glb_resources import relocate_glb
    from test.devtools.asset_design.test_glb_resources import fixture

    _, source, _, resources = fixture(tmp_path)
    target = tmp_path / "layouts/pod_bedroom/versions/v001/model.glb"
    target.parent.mkdir(parents=True)
    target.write_bytes(relocate_glb(source, target, root=tmp_path))
    relative = target.relative_to(tmp_path).as_posix()
    files = [target, *resources]
    save_catalog(
        tmp_path,
        {
            "assets": [
                {
                    "id": "example",
                    "title": "Example",
                    "category": "layout",
                    "designObject": {
                        "id": "layout:pod",
                        "label": "Example",
                        "group": "layout",
                        "collection": "layouts",
                    },
                    "designVersion": {"id": "example", "file": relative, "revision": 1},
                    "files": [
                        {
                            "path": p.relative_to(tmp_path).as_posix(),
                            "name": p.name,
                            "kind": "data",
                            "bytes": p.stat().st_size,
                        }
                        for p in files
                    ],
                }
            ]
        },
    )
    assert not inventory(tmp_path)["issues"]
    payload = resources[0].read_bytes()
    resources[0].write_bytes(bytes([payload[0] ^ 1]) + payload[1:])
    assert inventory(tmp_path)["issues"]
    resources[0].write_bytes(payload)
    assert not inventory(tmp_path)["issues"]
