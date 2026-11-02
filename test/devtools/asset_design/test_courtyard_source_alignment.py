"""The editable courtyard and its confirmation retain the accepted world inputs."""

import hashlib
import json
from pathlib import Path

from devtools.asset_design.catalog import ASSET_ROOT
from devtools.asset_design.catalog_store import read_catalog
from devtools.asset_design.design_models import read_model
from devtools.asset_design.object_content import content_digest

REPOSITORY = Path(__file__).resolve().parents[3]
SITE = ASSET_ROOT / "landscape/site"


def test_courtyard_source_tracks_current_runtime_inputs():
    build = json.loads((SITE / "source/build.json").read_text())
    inputs = build["runtimeAlignment"]["inputs"]
    assert "godot_project/rooms/estate/ElfieNest-complete-final.glb" in inputs
    assert "godot_project/rooms/estate/estate_outdoor_lighting.scn" in inputs
    assert "godot_project/rooms/estate/estate_shore_finish.gd" in inputs
    for relative, digest in inputs.items():
        assert (
            hashlib.sha256((REPOSITORY / relative).read_bytes()).hexdigest() == digest
        )


def test_latest_courtyard_is_editable_without_overwriting_confirmation():
    state = json.loads((ASSET_ROOT / "adoptions.json").read_text())
    selected = state["current"]["landscape:site"]
    assets = [
        asset
        for asset in read_catalog(ASSET_ROOT)["assets"]
        if (asset.get("designObject") or {}).get("id") == "landscape:site"
    ]
    latest = max(assets, key=lambda asset: asset["designVersion"]["revision"])
    version = latest["designVersion"]
    confirmed = next(
        asset["designVersion"]
        for asset in assets
        if asset["designVersion"]["id"] == selected["version"]
    )
    assert selected["contentDigest"] == confirmed["contentDigest"]
    relative = "landscape/site/source/model.glb"
    records, _ = read_model(ASSET_ROOT, relative)
    digest = content_digest(ASSET_ROOT, relative, [r["node"] for r in records])
    assert digest == version["contentDigest"]
    build = json.loads((SITE / "source/build.json").read_text())
    assert build["forestTrail"]["width_m"] == 1.5
    assert build["landscapeRegions"]["regionCount"] > 0
