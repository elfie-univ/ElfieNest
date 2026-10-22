"""Catalogue polling and shared-resource delivery stay cheap and current."""

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from devtools.asset_design.app import create_app
from devtools.asset_design.catalog_store import save_catalog as store_catalog
from devtools.asset_design.glb_resources import encode_glb


def save_catalog(root, assets):
    store_catalog(root, {"assets": assets})


def test_catalog_unchanged_poll_returns_no_body_and_changes_remain_visible(tmp_path):
    save_catalog(tmp_path, [])
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert client.get("/assets/design/catalog-request.mjs").status_code == 200
        first = client.get("/assets/design/catalog.json")
        assert first.status_code == 200
        assert "etag" in first.headers
        unchanged = client.get(
            "/assets/design/catalog.json",
            headers={"If-None-Match": first.headers["etag"]},
        )
        assert unchanged.status_code == 304 and not unchanged.content
        save_catalog(tmp_path, [{"id": "new", "title": "New", "category": "kit"}])
        changed = client.get(
            "/assets/design/catalog.json",
            headers={"If-None-Match": first.headers["etag"]},
        )
        assert changed.status_code == 200
        assert changed.json()["assets"][0]["id"] == "new"


def test_shared_hash_resources_can_be_cached_but_editable_files_cannot(tmp_path):
    data = b"shared payload"
    relative = (
        "furniture/shared_resources/source/resources/"
        + hashlib.sha256(data).hexdigest()
        + ".bin"
    )
    resource = tmp_path / relative
    resource.parent.mkdir(parents=True)
    resource.write_bytes(data)
    (tmp_path / "source.glb").write_bytes(b"editable")
    save_catalog(
        tmp_path,
        [
            {
                "id": "part",
                "title": "Part",
                "category": "kit",
                "files": [
                    {"path": path, "name": Path(path).name, "kind": "data", "bytes": 1}
                    for path in [relative, "source.glb"]
                ],
            }
        ],
    )
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        shared = client.get("/assets/design/files/" + relative)
        assert shared.content == data
        assert "immutable" in shared.headers["cache-control"]
        assert (
            client.get("/assets/design/files/source.glb").headers["cache-control"]
            == "no-store"
        )


def test_large_index_reuses_validated_models_and_invalidates_changed_model(
    tmp_path, monkeypatch
):
    doc = {
        "asset": {"version": "2.0"},
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {}}]}],
    }
    assets = []
    for index in range(140):
        name = f"furniture/{index}/versions/v001/model.glb"
        (tmp_path / name).parent.mkdir(parents=True)
        (tmp_path / name).write_bytes(encode_glb(doc))
        assets.append(
            {
                "id": str(index),
                "title": name,
                "category": "kit",
                "designObject": {
                    "id": f"part:{index}",
                    "label": name,
                    "group": "kit",
                    "collection": "parts",
                },
                "designVersion": {"id": str(index), "file": name, "revision": 1},
            }
        )
    save_catalog(tmp_path, assets)
    original = Path.read_bytes
    reads = []

    def read(path):
        if path.suffix == ".glb":
            reads.append(path)
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        first = client.get("/assets/design/design/index")
        assert first.status_code == 200 and not first.json()["issues"]
        reads.clear()
        second = client.get("/assets/design/design/index")
        assert second.status_code == 200 and not reads
        changed = dict(doc, nodes=[{"mesh": 0, "translation": [1, 0, 0]}])
        (tmp_path / "furniture/0/versions/v001/model.glb").write_bytes(
            encode_glb(changed)
        )
        third = client.get("/assets/design/design/index")
        assert third.status_code == 200 and not third.json()["issues"]
        assert set(reads) == {tmp_path / "furniture/0/versions/v001/model.glb"}

        def digest(response):
            return next(o for o in response.json()["objects"] if o["id"] == "part:0")[
                "versions"
            ][0]["contentDigest"]

        assert digest(first) != digest(third)
