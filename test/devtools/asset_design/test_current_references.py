"""Confirmation owns one object; references follow independently confirmed objects."""

import json

from fastapi.testclient import TestClient

from devtools.asset_design.app import create_app
from devtools.asset_design.catalog_store import read_catalog, save_catalog
from devtools.asset_design.design import assert_not_adopted
from devtools.asset_design.glb_resources import encode_glb, read_glb
from devtools.asset_design.object_assets import publish_object, split_assets
from test.devtools.asset_design.test_design import confirm, open_scene, setup
from test.devtools.asset_design.test_template_instances import prepare
from test.devtools.asset_design.test_working_drafts import draft


def test_references_require_confirmation_and_ignore_saved_version_pins(tmp_path):
    setup(tmp_path)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert not any(
            e["reference"] for e in open_scene(client, "layout:pod")["layers"]
        )
        assert (
            confirm(client, open_scene(client, "building:pod", "v1")).status_code == 200
        )
        split_assets(tmp_path)
        catalog = read_catalog(tmp_path)
        for asset in catalog["assets"]:
            if asset.get("designObject", {}).get("id") == "layout:pod":
                asset["designVersion"]["previewReferences"] = [
                    {"object": "building:pod", "version": "missing-old-version"}
                ]
        save_catalog(tmp_path, catalog)
        layout = open_scene(client, "layout:pod")
        assert next(e for e in layout["layers"] if e["reference"])["version"] == "v1"
        assert confirm(client, layout).status_code == 200
        assert (
            confirm(client, open_scene(client, "building:pod", "v2")).status_code == 200
        )
        refreshed = open_scene(client, "layout:pod")
        assert next(e for e in refreshed["layers"] if e["reference"])["version"] == "v2"
        assert refreshed["adopted"]
        record = json.loads((tmp_path / "adoptions.json").read_text())["current"][
            "layout:pod"
        ]
        assert "refs" not in record and "templates" not in record


def test_confirm_draft_only_freezes_the_selected_object(tmp_path):
    setup(tmp_path)
    split_assets(tmp_path)
    before = read_catalog(tmp_path)
    draft(tmp_path, 3)
    draft(tmp_path, 5, "layouts/pod_bedroom")
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        scene = open_scene(client, "building:pod", "draft")
        assert not any(e["reference"] for e in scene["layers"])
        result = confirm(client, scene)
        assert result.status_code == 200, result.text
        assert "refs" not in result.json() and "templates" not in result.json()
        assert len(read_catalog(tmp_path)["assets"]) == len(before["assets"]) + 1
        assert open_scene(client, "layout:pod", "draft")["layers"][0]["draft"]


def test_furniture_uses_confirmed_mother_without_invalidating_host_adoption(tmp_path):
    host, mother = prepare(tmp_path)
    publish_object(tmp_path, "layout:pod")
    before = host.read_bytes()
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert (
            confirm(client, open_scene(client, "part:common_chair")).status_code == 200
        )
        original = open_scene(client, "layout:pod")
        assert confirm(client, original).status_code == 200
        first = original["templates"][0]["version"]
        doc, binary = read_glb(mother / "model.glb")
        doc["nodes"][0]["extras"]["finish"] = "new"
        (mother / "model.glb").write_bytes(encode_glb(doc, binary))
        publish_object(tmp_path, "part:common_chair")
        unchanged = open_scene(client, "layout:pod")
        assert unchanged["templates"][0]["version"] == first
        assert unchanged["adopted"]
        assert (
            confirm(client, open_scene(client, "part:common_chair")).status_code == 200
        )
        updated = open_scene(client, "layout:pod")
        assert updated["templates"][0]["version"] != first
        assert updated["adopted"]
        assert confirm(client, unchanged).status_code == 200
        assert host.read_bytes() == before


def test_history_and_foreign_records_do_not_protect_old_revision(tmp_path):
    setup(tmp_path)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert (
            confirm(client, open_scene(client, "building:pod", "v1")).status_code == 200
        )
        assert (
            confirm(client, open_scene(client, "building:pod", "v2")).status_code == 200
        )
    assert_not_adopted(tmp_path, "v1")


def test_unconfirmed_mother_does_not_silently_supply_a_preview(tmp_path):
    prepare(tmp_path)
    publish_object(tmp_path, "layout:pod")
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        response = client.get(
            "/assets/design/design/scene", params={"object": "layout:pod"}
        )
        assert response.status_code == 409
        assert "not confirmed" in response.json()["detail"]
