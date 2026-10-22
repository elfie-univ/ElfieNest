"""Mutable source previews publish only after an explicit confirmation."""

import json

from fastapi.testclient import TestClient

from devtools.asset_design.app import create_app
from devtools.asset_design.catalog_store import read_catalog
from devtools.asset_design.glb_resources import encode_glb, read_glb
from devtools.asset_design.object_assets import split_assets
from test.devtools.asset_design.test_design import confirm, open_scene, setup


def draft(root, offset, folder="buildings/pod"):
    source = root / folder / "source/model.glb"
    doc, binary = read_glb(source)
    next(n for n in doc["nodes"] if "mesh" in n)["translation"] = [offset, 0, 0]
    source.write_bytes(encode_glb(doc, binary))
    path = source.with_name("build.json")
    build = json.loads(path.read_text())
    build["workingDraft"] = True
    path.write_text(json.dumps(build))


def test_draft_replaces_one_preview_without_allocating_versions(tmp_path):
    setup(tmp_path)
    split_assets(tmp_path)
    before = (tmp_path / "catalog.json").read_bytes()
    before_rows = read_catalog(tmp_path)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        draft(tmp_path, 3)
        first = open_scene(client, "building:pod", "draft")
        assert first["layers"][0]["file"] == "buildings/pod/source/model.glb"
        assert first["confirmable"] and not first["adopted"]
        draft(tmp_path, 4)
        second = open_scene(client, "building:pod", "draft")
        assert first["id"] != second["id"]
        index = client.get("/assets/design/design/index").json()
        versions = next(o for o in index["objects"] if o["id"] == "building:pod")[
            "versions"
        ]
        assert len([v for v in versions if v.get("draft")]) == 1
        assert (tmp_path / "catalog.json").read_bytes() == before
        assert not (tmp_path / "adoptions.json").exists()
        assert confirm(client, first).status_code == 409
        assert (tmp_path / "catalog.json").read_bytes() == before
        response = confirm(client, second)
        assert response.status_code == 200, response.text
        record = response.json()
        assert record["version"] != "draft"
        after = read_catalog(tmp_path)
        assert len(after["assets"]) == len(before_rows["assets"]) + 1
        assert open_scene(client, "building:pod")["adopted"]
        assert confirm(client, second).status_code == 409


def test_source_without_draft_marker_does_not_change_preview(tmp_path):
    setup(tmp_path)
    split_assets(tmp_path)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert not any(
            v.get("draft")
            for o in client.get("/assets/design/design/index").json()["objects"]
            for v in o["versions"]
        )


def test_confirm_freezes_only_selected_draft(tmp_path):
    setup(tmp_path)
    split_assets(tmp_path)
    before = read_catalog(tmp_path)
    draft(tmp_path, 3)
    draft(tmp_path, 5, "layouts/pod_bedroom")
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        plan = open_scene(client, "building:pod", "draft")
        assert not any(e["reference"] for e in plan["layers"])
        result = confirm(client, plan)
        assert result.status_code == 200, result.text
        assert "refs" not in result.json()
        assert set(
            json.loads((tmp_path / "adoptions.json").read_text())["current"]
        ) == {"building:pod"}
        assert len(read_catalog(tmp_path)["assets"]) == len(before["assets"]) + 1
