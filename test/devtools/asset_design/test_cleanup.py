"""Retire the marking page while preserving marks and saved asset access."""

import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from devtools.asset_design.app import create_app


def saved_assets(root):
    model = root / "room.glb"
    model.write_bytes(b"keep original model")
    catalog = root / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "id": "room_v1",
                        "category": "pod",
                        "title": "Room v1",
                        "files": [
                            {
                                "path": "room.glb",
                                "name": "room.glb",
                                "kind": "model",
                                "bytes": 19,
                            }
                        ],
                    },
                    {"id": "image_v2", "category": "reference", "title": "Image v2"},
                ]
            }
        )
    )
    return model, catalog


def test_retired_pages_are_unavailable_and_design_assets_remain(tmp_path):
    model, catalog = saved_assets(tmp_path)
    originals = [path.read_bytes() for path in (model, catalog)]
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        for path in (
            "/assets/cleanup",
            "/assets/cleanup/cleanup.html",
            "/assets/cleanup/cleanup.js",
            "/assets/cleanup/cleanup.css",
            "/assets/cleanup/cleanup-state.mjs",
        ):
            assert client.get(path).status_code == 404
        assert client.get("/assets/design").status_code == 200
        assert client.get("/assets/design/cleanup-state.mjs").status_code == 200
        assert client.get("/assets/design/files/room.glb").content == originals[0]
    assert [path.read_bytes() for path in (model, catalog)] == originals


def test_cleanup_marks_survive_restart_and_undo_without_touching_assets(tmp_path):
    model, catalog = saved_assets(tmp_path)
    originals = [path.read_bytes() for path in (model, catalog)]
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert client.get("/assets/cleanup/marks").json() == {"markedIds": []}
        response = client.put("/assets/cleanup/marks/room_v1", json={"marked": True})
        assert response.status_code == 200
        assert response.json() == {"markedIds": ["room_v1"]}
        assert (
            client.put(
                "/assets/cleanup/marks/image_v2", json={"marked": True}
            ).status_code
            == 200
        )
        assert len(client.get("/assets/design/catalog.json").json()["assets"]) == 2
        assert client.get("/assets/design").status_code == 200
        assert client.get("/assets/design/files/.cleanup-marks.json").status_code == 404
        assert client.delete("/assets/cleanup/marks/room_v1").status_code == 405
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert client.get("/assets/cleanup/marks").json() == {
            "markedIds": ["image_v2", "room_v1"]
        }
        assert client.put(
            "/assets/cleanup/marks/room_v1", json={"marked": False}
        ).json() == {"markedIds": ["image_v2"]}
    assert [path.read_bytes() for path in (model, catalog)] == originals


def test_cleanup_rejects_unknown_assets_and_cross_origin_marking(tmp_path):
    saved_assets(tmp_path)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert (
            client.put(
                "/assets/cleanup/marks/unknown", json={"marked": True}
            ).status_code
            == 404
        )
        for headers in (
            {"origin": "https://evil.example"},
            {"sec-fetch-site": "cross-site"},
        ):
            assert (
                client.put(
                    "/assets/cleanup/marks/room_v1",
                    json={"marked": True},
                    headers=headers,
                ).status_code
                == 403
            )
        assert (
            client.put(
                "/assets/cleanup/marks/room_v1",
                json={"marked": True},
                headers={"origin": "http://127.0.0.1"},
            ).status_code
            == 200
        )
        assert client.get("/assets/cleanup/../catalog.json").status_code == 404


def test_cleanup_list_preview_and_export_keep_each_marked_version():
    repository = Path(__file__).resolve().parents[3]
    subprocess.run(
        ["node", "--test", str(Path(__file__).with_name("cleanup.test.mjs"))],
        cwd=repository,
        check=True,
    )
