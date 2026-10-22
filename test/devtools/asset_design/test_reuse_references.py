"""Compacted build inputs share immutable audit details across publications."""

import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from devtools.asset_design.app import create_app
from devtools.asset_design.catalog_store import read_catalog
from devtools.asset_design.deletion import delete_asset
from devtools.asset_design.glb_resources import encode_glb, read_glb
from devtools.asset_design.object_assets import publish_object
from test.devtools.asset_design.test_shared_publication import prepare


def test_publish_reuses_details_and_deleting_original_version_keeps_them(tmp_path):
    identifier, source, build, _, _ = prepare(tmp_path)
    build["reuse"] = {
        "identity": "plant",
        "sourceReferences": 1,
        "occurrences": [{"sceneObject": "layout:pod"}],
        "resources": [],
    }
    source.with_name("build.json").write_text(json.dumps(build))
    publish_object(tmp_path, identifier, label="Shared plant")
    first = read_catalog(tmp_path)["assets"][0]
    relative = first["designVersion"]["reuse"]["details"]
    before = (tmp_path / relative).read_bytes()
    build["reuse"] = {
        k: v for k, v in build["reuse"].items() if k not in {"occurrences", "resources"}
    }
    build["reuse"]["details"] = relative
    source.with_name("build.json").write_text(json.dumps(build))
    doc, binary = read_glb(source)
    doc["nodes"][0]["translation"] = [8, 0, 0]
    source.write_bytes(encode_glb(doc, binary))
    second = publish_object(tmp_path, identifier)
    row = read_catalog(tmp_path)["assets"][-1]
    assert row["designVersion"]["reuse"]["details"] == relative
    assert any(f["path"] == relative for f in row["files"])
    assert not (tmp_path / second["file"]).with_name("reuse.json").exists()
    delete_asset(tmp_path, first["id"])
    assert (tmp_path / relative).read_bytes() == before
    assert all(a["id"] != first["id"] for a in read_catalog(tmp_path)["assets"])
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert client.get("/assets/design/files/" + relative).content == before
        assert (
            client.get(
                "/assets/design/design/scene", params={"object": identifier}
            ).status_code
            == 200
        )
    assert publish_object(tmp_path, identifier)["changed"] is False


@pytest.mark.parametrize(
    "problem",
    ["missing", "escape", "other_owner", "invalid_json", "invalid_shape", "mixed"],
)
def test_bad_detail_reference_fails_before_publishing_files(tmp_path, problem):
    identifier, source, build, _, _ = prepare(tmp_path)
    relative = "furniture/example_plant/versions/v001/reuse.json"
    report = tmp_path / relative
    report.parent.mkdir(parents=True)
    if problem != "missing":
        report.write_text(
            "{bad"
            if problem == "invalid_json"
            else json.dumps(
                {"occurrences": {}, "resources": []}
                if problem == "invalid_shape"
                else {"occurrences": [], "resources": []}
            )
        )
    if problem == "escape":
        relative = "../outside.json"
    elif problem == "other_owner":
        other = tmp_path / "furniture/another/versions/v001/reuse.json"
        other.parent.mkdir(parents=True)
        other.write_text(json.dumps({"occurrences": [], "resources": []}))
        relative = other.relative_to(tmp_path).as_posix()
    build["reuse"] = {"details": relative}
    if problem == "mixed":
        build["reuse"]["occurrences"] = []
    source.with_name("build.json").write_text(json.dumps(build))
    before = (tmp_path / "catalog.json").read_bytes()
    with pytest.raises((ValueError, OSError, HTTPException)):
        publish_object(tmp_path, identifier, label="Shared plant")
    assert (tmp_path / "catalog.json").read_bytes() == before
    assert not report.with_name("model.glb").exists()
