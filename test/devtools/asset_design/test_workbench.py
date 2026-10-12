"""Protect the single asset workbench and its read-only file boundary."""

import hashlib
import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from devtools.asset_design.app import create_app


def test_asset_page_is_independent_and_only_serves_registered_assets(tmp_path) -> None:
    model = tmp_path / "room" / "room.glb"
    model.parent.mkdir()
    model.write_bytes(b"registered model")
    (tmp_path / "secret.txt").write_text("must not be served")
    (tmp_path / "catalog.json").write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "id": "room",
                        "category": "pod",
                        "title": "房间",
                        "primaryModel": "room/room.glb",
                        "models": ["room/room.glb"],
                        "files": [
                            {
                                "path": "room/room.glb",
                                "name": "room.glb",
                                "kind": "model",
                                "bytes": 16,
                            }
                        ],
                    }
                ],
                "stats": {},
            }
        )
    )
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        page = client.get("/assets/design")
        assert page.status_code == 200
        assert page.headers["cache-control"] == "no-store"
        assert 'id="assetSelect"' in page.text
        assert 'id="viewer"' in page.text
        catalog = client.get("/assets/design/catalog.json").json()
        assert catalog["assets"][0]["primaryModel"] == "room/room.glb"
        assert (
            client.get("/assets/design/files/room/room.glb").content
            == model.read_bytes()
        )
        assert client.get("/assets/design/files/secret.txt").status_code == 404
        assert (
            client.get("/assets/design/files/room/old-viewer.html").status_code == 404
        )
        assert client.get("/api/elfies").status_code == 404
        assert client.get("/godot-web/elfienest.html").status_code == 404
        assert (
            client.get("/assets/design", headers={"host": "evil.example"}).status_code
            == 400
        )


def test_empty_asset_directory_keeps_the_workbench_available(tmp_path) -> None:
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert client.get("/assets/design").status_code == 200
        assert client.get("/assets/design/catalog.json").json()["assets"] == []


def test_experiment_service_and_menu_do_not_mount_the_asset_workbench() -> None:
    repository = Path(__file__).resolve().parents[3]
    static_host = (repository / "devtools/elfie_lab/static_host.py").read_text()
    menu = (repository / "devtools/web/src/ui/GlobalLabNav.tsx").read_text()
    assert "devtools.asset_design" not in static_host
    assert "asset-design" not in menu
    assert "/assets/design" not in menu


def test_fixed_layout_styles_match_the_approved_baseline() -> None:
    fixtures = Path(__file__).parent / "fixtures"
    baseline = json.loads((fixtures / "approved-layout.json").read_text())
    web = Path(__file__).resolve().parents[3] / "devtools" / "asset_design" / "web"
    for name in ("library.css", "viewer.css"):
        assert hashlib.sha256((web / name).read_bytes()).hexdigest() == baseline[name]
    assert (fixtures / "approved-layout.png").is_file()


def test_view_filters_keep_other_rooms_and_hidden_furniture_out() -> None:
    web = Path(__file__).resolve().parents[3] / "devtools" / "asset_design" / "web"
    program = """
      import {meshVisible} from './view-state.mjs';
      import assert from 'node:assert/strict';
      const view={module:'M01',floor:'2',section:true,glass:false,scale:false,furniture:true};
      assert(meshVisible({module:'M01',floor:2,furniture:true},view));
      assert(!meshVisible({module:'M02',floor:2},view));
      assert(!meshVisible({module:'M01',floor:1},view));
      assert(!meshVisible({module:'M01',floor:2,section_hide:true},view));
      assert(!meshVisible({module:'M01',floor:2,glass:true},view));
      assert(!meshVisible({module:'M01',floor:2,reference:true},view));
      assert(!meshVisible({module:'M01',floor:2,furniture:true},{...view,furniture:false}));
      for(let i=1;i<=8;i++) {
        const module='M'+String(i).padStart(2,'0');
        assert(meshVisible({module,floor:2},{...view,module}));
      }
    """
    subprocess.run(["node", "--input-type=module", "-e", program], cwd=web, check=True)


def test_catalog_rejects_a_registered_path_outside_the_asset_root(tmp_path) -> None:
    outside = tmp_path.parent / "outside.glb"
    outside.write_bytes(b"private")
    (tmp_path / "escape.glb").symlink_to(outside)
    (tmp_path / "catalog.json").write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "id": "escape",
                        "title": "escape",
                        "category": "pod",
                        "models": ["escape.glb"],
                        "primaryModel": "escape.glb",
                        "files": [
                            {
                                "path": "escape.glb",
                                "name": "escape.glb",
                                "kind": "model",
                                "bytes": 7,
                            }
                        ],
                    }
                ],
                "stats": {},
            }
        )
    )
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert client.get("/assets/design/files/escape.glb").status_code == 404


def test_approved_viewer_controls_remain_in_the_right_sidebar(tmp_path) -> None:
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        page = client.get("/assets/design/viewer.html").text
        sidebar = page.split("<aside>", 1)[1].split("</aside>", 1)[0]
        for control in (
            "whole",
            "section",
            "glass",
            "scale",
            "furniture",
            "dimensions",
            "ruler",
            "floor",
            "module",
            "reset",
            "front",
            "top",
            "rear",
            "side",
            "zoomIn",
            "zoomOut",
            "day",
            "dusk",
            "download",
        ):
            assert f'id="{control}"' in sidebar
        assert 'id="objectControls"' in page
        assert 'id="floorControls"' in page
        script = client.get("/assets/design/viewer.js").text
        assert "__PAYLOAD__" not in page
        assert "estate_v30.glb" not in script
        assert "measurements.anchors" in script
        library = client.get("/assets/design/library.js").text
        assert "url(asset.viewer)" not in library
        assert "/assets/design/viewer.html" in library
        assert "sharedPreview?" not in library


def test_asset_command_does_not_construct_the_experiment_app(monkeypatch) -> None:
    import devtools.__main__ as developer_main
    import devtools.asset_design.app as asset_app

    opened = []
    monkeypatch.setattr(developer_main, "restart_default_lab", lambda *_args: None)
    monkeypatch.setattr(asset_app, "create_app", lambda *_args: "asset-only")
    monkeypatch.setattr(developer_main.webbrowser, "open", opened.append)
    monkeypatch.setattr(
        developer_main.uvicorn,
        "run",
        lambda app, **kwargs: (
            (app == "asset-only") or (_ for _ in ()).throw(AssertionError(app))
        ),
    )
    assert developer_main.main(["asset-design"]) == 0
    assert opened == ["http://127.0.0.1:9001/assets/design"]
