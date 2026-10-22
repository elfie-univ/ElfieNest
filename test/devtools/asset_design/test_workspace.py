"""Design assets remain portable and publish into their object-owned directories."""

from pathlib import Path

from fastapi.testclient import TestClient

from devtools.asset_design.app import create_app
from devtools.asset_design.catalog import ASSET_ROOT
from devtools.asset_design.catalog_store import read_catalog, save_catalog
from devtools.asset_design.object_assets import publish_object, split_assets
from devtools.asset_design.workspace import audit_workspace, organize_workspace
from test.devtools.asset_design.test_design import confirm, open_scene, setup


def test_workspace_relocates_versions_images_and_confirmations_without_legacy_root(
    tmp_path,
):
    old, target = tmp_path / "old", tmp_path / "new"
    old.mkdir()
    setup(old)
    with TestClient(create_app(old), base_url="http://127.0.0.1") as client:
        confirm(client, open_scene(client, "building:pod", "v2"))
    split_assets(old)
    catalog = read_catalog(old)
    (old / "reference.png").write_bytes(b"reference")
    catalog["imageReferences"] = [
        {
            "path": "reference.png",
            "objects": ["building:pod"],
            "title": "Pod",
            "kind": "reference",
        }
    ]
    save_catalog(old, catalog)
    before = (old / "adoptions.json").read_bytes()
    organize_workspace(old, target)
    assert (target / "adoptions.json").read_bytes() == before
    assert (target / "buildings/pod/versions/v002/model.glb").is_file()
    assert (target / "buildings/pod/source/model.glb").is_file()
    assert (target / "buildings/pod/references/reference.png").is_file()
    old.rename(tmp_path / "unavailable")
    assert audit_workspace(target)["issues"] == []
    assert publish_object(target, "building:pod")["changed"] is False
    with TestClient(create_app(target), base_url="http://127.0.0.1") as client:
        assert open_scene(client, "building:pod", "v2")["adopted"]
        assert (
            client.get(
                "/assets/design/files/buildings/pod/references/reference.png"
            ).status_code
            == 200
        )


def test_workspace_fails_before_copying_missing_input(tmp_path):
    import pytest

    old = tmp_path / "old"
    old.mkdir()
    setup(old)
    split_assets(old)
    missing = old / "buildings/pod/source/model.glb"
    missing.unlink()
    target = tmp_path / "new"
    with pytest.raises(ValueError, match="Missing"):
        organize_workspace(old, target)
    assert not target.exists()


def test_default_workspace_is_owned_by_design_tool():
    assert (
        ASSET_ROOT
        == Path(__file__).resolve().parents[3] / "devtools/asset_design/assets"
    )


def test_publishing_registers_generated_images_without_changing_confirmation(tmp_path):
    old, target = tmp_path / "old", tmp_path / "new"
    old.mkdir()
    setup(old)
    split_assets(old)
    organize_workspace(old, target)
    image = tmp_path / "new-render.png"
    image.write_bytes(b"generated picture")
    result = publish_object(target, "building:pod", images=[image])
    assert result["changed"] is False
    catalog = read_catalog(target)
    ref = catalog["imageReferences"][0]
    assert ref["objects"] == ["building:pod"]
    assert ref["kind"] == "render"
    assert ref["path"] == "buildings/pod/versions/v002/images/new-render.png"
    assert (target / ref["path"]).read_bytes() == image.read_bytes()
    assert audit_workspace(target)["issues"] == []


def test_workspace_preserves_shared_resource_paths_when_relocated(tmp_path):
    from devtools.asset_design.object_assets import publish_object
    from test.devtools.asset_design.test_shared_publication import (
        prepare as prepare_shared,
    )

    old = tmp_path / "old"
    old.mkdir()
    identifier, _, _, resources, _ = prepare_shared(old)
    publish_object(old, identifier, label="公共盆栽")

    target = tmp_path / "new"
    organize_workspace(old, target)

    assert audit_workspace(target)["issues"] == []
    assert all((target / resource.relative_to(old)).is_file() for resource in resources)
