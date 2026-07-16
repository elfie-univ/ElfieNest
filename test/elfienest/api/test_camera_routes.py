from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from elfienest.api.app import create_app
from elfienest.persistence.store import init_db

from ._helpers import create_test_admin

JPEG_FRAME = b"\xff\xd8camera-frame\xff\xd9"


@pytest.fixture
def client(tmp_path: Path):
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_test_admin(db_path)
    with (
        patch("elfienest.api.app.AuthenticatedWSManager.start"),
        patch("elfienest.api.app.AuthenticatedWSManager.stop"),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        with TestClient(application) as test_client:
            yield test_client


def _login(client: TestClient) -> str:
    response = client.post(
        "/api/auth/login",
        data={"username": "admin", "password": "adminchangeme"},
    )
    assert response.status_code == 200
    return response.headers["X-CSRF-Token"]


def test_camera_status_requires_login(client: TestClient) -> None:
    assert client.get("/api/camera/status").status_code == 401
    assert client.get("/api/camera/frame.jpg").status_code == 401


def test_godot_frame_and_camera_control_round_trip(client: TestClient) -> None:
    status_response = client.post(
        "/api/godot-camera/status",
        json={
            "labels": ["整体总览", "区域俯视 01-04", "01 厨房"],
            "active_index": 0,
            "bed_count": 4,
        },
    )
    frame_response = client.post(
        "/api/godot-camera/frame?view_index=0",
        content=JPEG_FRAME,
        headers={"Content-Type": "image/jpeg"},
    )
    csrf_token = _login(client)

    viewer_status = client.get("/api/camera/status")
    image_response = client.get("/api/camera/frame.jpg")
    selection_response = client.put(
        "/api/camera/view",
        json={"index": 2},
        headers={"X-CSRF-Token": csrf_token},
    )
    control_response = client.get("/api/godot-camera/control")

    assert status_response.status_code == 200
    assert frame_response.status_code == 200
    assert viewer_status.status_code == 200
    assert viewer_status.json()["online"] is True
    assert viewer_status.json()["labels"] == ["整体总览", "区域俯视 01-04", "01 厨房"]
    assert viewer_status.json()["reported_bed_count"] == 4
    assert viewer_status.json()["layout_syncing"] is False
    assert image_response.status_code == 200
    assert image_response.content == JPEG_FRAME
    assert image_response.headers["cache-control"].startswith("no-store")
    assert selection_response.json() == {"view_index": 2}
    assert control_response.json() == {"view_index": 2, "bed_count": 4}


def test_camera_rejects_invalid_frames_and_view_indexes(client: TestClient) -> None:
    invalid_frame = client.post(
        "/api/godot-camera/frame",
        content=b"not-jpeg",
        headers={"Content-Type": "image/jpeg"},
    )
    client.post(
        "/api/godot-camera/status",
        json={"labels": ["整体总览"], "active_index": 0, "bed_count": 4},
    )
    csrf_token = _login(client)
    invalid_view = client.put(
        "/api/camera/view",
        json={"index": 1},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert invalid_frame.status_code == 422
    assert invalid_view.status_code == 422


def test_camera_status_reports_layout_syncing_until_godot_rebuilds(
    client: TestClient,
) -> None:
    csrf_token = _login(client)
    update_response = client.put(
        "/api/admin/nest/rooms/default/bed-count",
        json={"bed_count": 12},
        headers={"X-CSRF-Token": csrf_token},
    )
    control_response = client.get("/api/godot-camera/control")
    client.post(
        "/api/godot-camera/status",
        json={"labels": ["整体总览"], "active_index": 0, "bed_count": 4},
    )
    syncing_status = client.get("/api/camera/status")
    client.post(
        "/api/godot-camera/status",
        json={"labels": ["整体总览"], "active_index": 0, "bed_count": 12},
    )
    synced_status = client.get("/api/camera/status")

    assert update_response.status_code == 200
    assert control_response.json() == {"view_index": 0, "bed_count": 12}
    assert syncing_status.json()["desired_bed_count"] == 12
    assert syncing_status.json()["reported_bed_count"] == 4
    assert syncing_status.json()["layout_syncing"] is True
    assert synced_status.json()["layout_syncing"] is False
