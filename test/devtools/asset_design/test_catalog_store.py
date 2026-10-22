"""Object indexes reuse version records without changing the preview catalog."""

import copy
import json

import pytest

from devtools.asset_design.catalog_store import (
    read_catalog,
    save_catalog,
    snapshot_catalog,
)


def rows():
    result = []
    for name, revision in [("central", 1), ("pod", 1), ("central", 2)]:
        identifier = f"building_{name}_v{revision:03d}"
        file = f"buildings/{name}/versions/v{revision:03d}/model.glb"
        result.append(
            {
                "id": identifier,
                "title": identifier,
                "category": "building",
                "designObject": {"id": f"building:{name}", "label": name},
                "designVersion": {"id": identifier, "file": file, "revision": revision},
                "files": [
                    {
                        "path": "shared.png",
                        "name": "shared.png",
                        "kind": "image",
                        "bytes": revision,
                    }
                ],
            }
        )
    return {"assets": result, "imageReferences": [], "stats": {}, "extra": "preserved"}


def test_split_roundtrip_preserves_global_order_and_each_versions_metadata(tmp_path):
    original = rows()
    save_catalog(tmp_path, original)
    assert read_catalog(tmp_path) == original
    index = json.loads((tmp_path / "catalog.json").read_text())
    assert "assets" not in index
    assert len(index["objects"]) == 2
    obj = json.loads((tmp_path / "buildings/central/object.json").read_text())
    assert obj["designObject"] == original["assets"][0]["designObject"]
    assert len(obj["versions"]) == 2
    version = json.loads(
        (tmp_path / "buildings/central/versions/v001/version.json").read_text()
    )
    assert "designObject" not in version
    assert version["files"] == original["assets"][0]["files"]


def test_save_updates_only_changed_object_and_keeps_unlisted_version(tmp_path):
    data = rows()
    save_catalog(tmp_path, data)
    untouched = tmp_path / "buildings/pod/object.json"
    before = untouched.stat().st_mtime_ns
    unlisted = tmp_path / "buildings/central/versions/v099/version.json"
    unlisted.parent.mkdir()
    unlisted.write_text('{"not": "registered"}')
    data["assets"][0]["description"] = "Changed"
    save_catalog(tmp_path, data, expected=snapshot_catalog(tmp_path))
    assert untouched.stat().st_mtime_ns == before
    assert read_catalog(tmp_path) == data
    assert unlisted.read_text() == '{"not": "registered"}'


def test_removing_a_version_does_not_rewrite_other_object_indexes(tmp_path):
    data = rows()
    save_catalog(tmp_path, data)
    other = tmp_path / "buildings/pod/object.json"
    before = other.read_bytes()
    data["assets"].pop(0)
    save_catalog(tmp_path, data)
    assert other.read_bytes() == before
    assert read_catalog(tmp_path) == data


def test_deleting_last_version_archives_object_index_but_keeps_editable_source(
    tmp_path,
):
    from devtools.asset_design.deletion import delete_asset

    root = tmp_path / "assets"
    root.mkdir()
    data = rows()
    save_catalog(root, data)
    source = root / "buildings/pod/source/model.glb"
    source.parent.mkdir()
    source.write_bytes(b"editable")
    delete_asset(root, "building_pod_v001")
    assert not (root / "buildings/pod/object.json").exists()
    assert not (root / "buildings/pod/versions/v001/version.json").exists()
    assert source.read_bytes() == b"editable"
    assert len(read_catalog(root)["assets"]) == 2


def test_child_edit_is_detected_even_when_root_index_is_unchanged(tmp_path):
    data = rows()
    save_catalog(tmp_path, data)
    before = snapshot_catalog(tmp_path)
    version = tmp_path / "buildings/central/versions/v001/version.json"
    changed = json.loads(version.read_text())
    changed["title"] = "External edit"
    version.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="changed"):
        save_catalog(tmp_path, data, expected=before)
    assert json.loads(version.read_text())["title"] == "External edit"


def test_failed_save_restores_all_metadata(tmp_path, monkeypatch):
    from devtools.asset_design import catalog_store

    data = rows()
    save_catalog(tmp_path, data)
    before = snapshot_catalog(tmp_path)
    original_write = catalog_store.write_bytes

    def fail(path, content):
        if path == tmp_path / "buildings/pod/versions/v001/version.json":
            raise OSError("disk error")
        original_write(path, content)

    monkeypatch.setattr(catalog_store, "write_bytes", fail)
    changed = copy.deepcopy(data)
    for row in changed["assets"]:
        row["title"] = "Changed"
    with pytest.raises(OSError, match="disk error"):
        save_catalog(tmp_path, changed, expected=before)
    assert snapshot_catalog(tmp_path) == before


@pytest.mark.parametrize("relative", ["../outside.json", "/tmp/outside.json"])
def test_index_paths_cannot_escape_workspace(tmp_path, relative):
    (tmp_path / "catalog.json").write_text(
        json.dumps({"objects": [{"id": "building:central", "index": relative}]})
    )
    with pytest.raises(ValueError, match="path"):
        read_catalog(tmp_path)


def test_missing_registered_version_fails_instead_of_scanning_or_skipping(tmp_path):
    save_catalog(tmp_path, rows())
    (tmp_path / "buildings/central/versions/v001/version.json").unlink()
    with pytest.raises(FileNotFoundError):
        read_catalog(tmp_path)


def test_resource_authorization_invalidates_on_child_edit_without_root_edit(tmp_path):
    from devtools.asset_design.catalog import registered_file

    save_catalog(tmp_path, rows())
    (tmp_path / "shared.png").write_bytes(b"image")
    (tmp_path / "other.png").write_bytes(b"other")
    root_before = (tmp_path / "catalog.json").read_bytes()
    assert registered_file(tmp_path, "shared.png")
    assert registered_file(tmp_path, "other.png") is None
    version = tmp_path / "buildings/central/versions/v001/version.json"
    data = json.loads(version.read_text())
    data["files"].append(
        {"path": "other.png", "name": "other.png", "kind": "image", "bytes": 5}
    )
    version.write_text(json.dumps(data))
    assert (tmp_path / "catalog.json").read_bytes() == root_before
    assert registered_file(tmp_path, "other.png")


def test_known_resource_checks_owners_only_and_child_removal_revokes_access(
    tmp_path, monkeypatch
):
    from pathlib import Path

    from devtools.asset_design.catalog import registered_file

    data = rows()
    for row in data["assets"]:
        row["files"] = [
            {
                "path": row["id"] + ".png",
                "name": "image.png",
                "kind": "image",
                "bytes": 5,
            }
        ]
        (tmp_path / (row["id"] + ".png")).write_bytes(b"image")
    save_catalog(tmp_path, data)
    assert registered_file(tmp_path, "building_central_v001.png")
    original_stat = Path.stat

    def stat(path, *args, **kwargs):
        assert path != tmp_path / "buildings/pod/object.json"
        return original_stat(path, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "stat", stat)
        assert registered_file(tmp_path, "building_central_v001.png")
    version = tmp_path / "buildings/central/versions/v001/version.json"
    record = json.loads(version.read_text())
    record["files"] = []
    version.write_text(json.dumps(record))
    assert registered_file(tmp_path, "building_central_v001.png") is None


@pytest.mark.parametrize("fail_marks", [False, True])
def test_delete_archives_version_metadata_and_rolls_back_child_indexes(
    tmp_path, monkeypatch, fail_marks
):
    from devtools.asset_design import deletion

    root = tmp_path / "assets"
    root.mkdir()
    data = rows()
    for row in data["assets"]:
        relative = row["designVersion"]["file"]
        row["primaryModel"] = relative
        row["models"] = [relative]
        row["files"].append(
            {"path": relative, "name": "model.glb", "kind": "model", "bytes": 5}
        )
        model = root / relative
        model.parent.mkdir(parents=True)
        model.write_bytes(b"model")
    (root / "shared.png").write_bytes(b"image")
    save_catalog(root, data)
    before = snapshot_catalog(root)
    original_write = deletion.write_json

    def write(path, value):
        if fail_marks and path.name == ".cleanup-marks.json":
            raise OSError("marks failed")
        original_write(path, value)

    monkeypatch.setattr(deletion, "write_json", write)
    if fail_marks:
        with pytest.raises(OSError, match="marks failed"):
            deletion.delete_asset(root, "building_central_v001")
        assert snapshot_catalog(root) == before
        assert (
            root / "buildings/central/versions/v001/model.glb"
        ).read_bytes() == b"model"
    else:
        result = deletion.delete_asset(root, "building_central_v001")
        assert [a["id"] for a in read_catalog(root)["assets"]] == [
            "building_pod_v001",
            "building_central_v002",
        ]
        assert not (root / "buildings/central/versions/v001/version.json").exists()
        assert not (root / "buildings/central/versions/v001/model.glb").exists()
        assert (root / "shared.png").read_bytes() == b"image"
        archive = tmp_path / "asset_cleanup" / result["backup"]
        assert (archive / "files/buildings/central/versions/v001/version.json").exists()
