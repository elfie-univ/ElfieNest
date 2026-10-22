"""Direct deletion removes one version and keeps recoverable files and consumers."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from devtools.asset_design.app import create_app
from devtools.asset_design.catalog_store import read_catalog


def setup_assets(root):
    root.mkdir()
    files = {
        "kit/model.glb": b"model",
        "kit/shared.png": b"shared reference",
        "kit/source.blend": b"source",
        "kit/child.glb": b"other version in same directory",
        "kit/unregistered.txt": b"unrelated",
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(content)
    rows = [
        {"path": p, "name": Path(p).name, "kind": k, "bytes": len(files[p])}
        for p, k in (
            ("kit/model.glb", "model"),
            ("kit/shared.png", "image"),
            ("kit/source.blend", "source"),
        )
    ]
    catalog = {
        "extra": "preserve raw metadata",
        "assets": [
            {
                "id": "kit",
                "category": "furniture",
                "title": "Kit",
                "files": rows,
                "models": ["kit/model.glb"],
                "mtime_ns": 123,
            },
            {
                "id": "child",
                "category": "pod",
                "title": "Child",
                "files": [
                    {
                        "path": "kit/child.glb",
                        "name": "child.glb",
                        "kind": "model",
                        "bytes": 31,
                    }
                ],
                "models": ["kit/child.glb"],
                "referenceFloors": {"1": "kit/shared.png"},
                "mtime_ns": 456,
            },
        ],
    }
    (root / "catalog.json").write_text(json.dumps(catalog))
    (root / ".cleanup-marks.json").write_text(
        json.dumps({"markedIds": ["kit", "child"]})
    )
    return catalog, files


def test_delete_one_version_archives_outputs_keeps_shared_files_and_marks(tmp_path):
    root = tmp_path / "assets"
    original, files = setup_assets(root)
    with TestClient(create_app(root), base_url="http://127.0.0.1") as client:
        response = client.delete("/assets/cleanup/assets/kit")
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["deletedId"] == "kit"
        assert result["archivedFiles"] == 1
        assert client.get("/assets/cleanup/marks").json() == {"markedIds": ["child"]}
        assert client.get("/assets/design/files/kit/model.glb").status_code == 404
        assert (
            client.get("/assets/design/files/kit/shared.png").content
            == files["kit/shared.png"]
        )
    saved = read_catalog(root)
    assert saved["extra"] == original["extra"]
    assert [a["id"] for a in saved["assets"]] == ["child"]
    assert saved["assets"][0]["mtime_ns"] == 456
    assert saved["stats"]["models"] == 1
    assert saved["stats"]["images"] == 1
    assert saved["stats"]["directories"] == 1
    assert saved["stats"]["records"] == 1
    archive = root.parent / "asset_cleanup" / result["backup"]
    assert (archive / "files/kit/model.glb").read_bytes() == files["kit/model.glb"]
    assert json.loads((archive / "catalog.before.json").read_text()) == original
    report = json.loads((archive / "report.json").read_text())
    assert report["target"] == "kit"
    assert report["inventory"]
    assert report["references"]
    assert report["residuals"]
    for relative in (
        "kit/shared.png",
        "kit/child.glb",
        "kit/source.blend",
        "kit/unregistered.txt",
    ):
        assert (root / relative).read_bytes() == files[relative]


def test_delete_rejects_unknown_origin_and_unsafe_paths_without_mutation(tmp_path):
    root = tmp_path / "assets"
    setup_assets(root)
    before = (root / "catalog.json").read_bytes()
    with TestClient(create_app(root), base_url="http://127.0.0.1") as client:
        assert client.delete("/assets/cleanup/assets/unknown").status_code == 404
        for headers in (
            {"origin": "https://evil.example"},
            {"sec-fetch-site": "cross-site"},
        ):
            assert (
                client.delete("/assets/cleanup/assets/kit", headers=headers).status_code
                == 403
            )
        assert (root / "catalog.json").read_bytes() == before
        raw = json.loads(before)
        raw["assets"][0]["files"][0]["path"] = "../outside.glb"
        (root / "catalog.json").write_text(json.dumps(raw))
        assert client.delete("/assets/cleanup/assets/kit").status_code == 409
        assert (root / "kit/model.glb").is_file()


def test_delete_rolls_back_files_and_index_when_write_fails(tmp_path, monkeypatch):
    from devtools.asset_design import deletion

    root = tmp_path / "assets"
    setup_assets(root)
    original = (root / "catalog.json").read_bytes()
    marks = (root / ".cleanup-marks.json").read_bytes()
    real_write = deletion.write_json

    def fail_marks(path, data):
        if path == root / ".cleanup-marks.json":
            raise OSError("simulated write failure")
        real_write(path, data)

    monkeypatch.setattr(deletion, "write_json", fail_marks)
    with TestClient(
        create_app(root), base_url="http://127.0.0.1", raise_server_exceptions=False
    ) as client:
        assert client.delete("/assets/cleanup/assets/kit").status_code == 500
    assert (root / "catalog.json").read_bytes() == original
    assert (root / ".cleanup-marks.json").read_bytes() == marks
    assert (root / "kit/model.glb").read_bytes() == b"model"


@pytest.mark.parametrize("symlink", [False, True])
def test_delete_preserves_files_referenced_by_build_inputs(tmp_path, symlink):
    root = tmp_path / "assets"
    setup_assets(root)
    if symlink:
        outside = tmp_path / "outside.glb"
        outside.write_bytes(b"external")
        (root / "kit/model.glb").unlink()
        (root / "kit/model.glb").symlink_to(outside)
    else:
        (root / "build.py").write_text("source = 'kit/model.glb'")
    with TestClient(create_app(root), base_url="http://127.0.0.1") as client:
        response = client.delete("/assets/cleanup/assets/kit")
        assert response.status_code == (409 if symlink else 200)
    assert (root / "kit/model.glb").is_file()


def test_delete_last_picture_clears_catalog_and_preserves_unregistered_files(tmp_path):
    root = tmp_path / "assets"
    root.mkdir()
    (root / "photo.png").write_bytes(b"photo")
    (root / "untouched.png").write_bytes(b"unregistered")
    (root / "catalog.json").write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "id": "image_1111111111111111",
                        "category": "reference",
                        "title": "Photo",
                        "images": ["photo.png"],
                        "files": [
                            {
                                "path": "photo.png",
                                "name": "photo.png",
                                "kind": "image",
                                "bytes": 5,
                            }
                        ],
                    }
                ]
            }
        )
    )
    with TestClient(create_app(root), base_url="http://127.0.0.1") as client:
        assert (
            client.delete("/assets/cleanup/assets/image_1111111111111111").status_code
            == 200
        )
        catalog = client.get("/assets/design/catalog.json").json()
        assert catalog["assets"] == []
        assert catalog["stats"]["images"] == 0
    assert not (root / "photo.png").exists()
    assert (root / "untouched.png").read_bytes() == b"unregistered"
