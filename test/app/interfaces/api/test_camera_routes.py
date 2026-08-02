from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.persistence.store import init_db
from app.interfaces.api.app import create_app

from ._helpers import create_test_owner


@pytest.fixture
def client(tmp_path: Path):
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_test_owner(db_path)
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        with TestClient(application) as test_client:
            yield test_client


def _login(client: TestClient) -> str:
    response = client.post(
        "/api/auth/login",
        data={"account_id": "owner", "password": "ownerchangeme"},
    )
    assert response.status_code == 200
    return response.headers["X-CSRF-Token"]


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/camera/status"),
        ("get", "/api/camera/frame.jpg"),
        ("put", "/api/camera/view"),
        ("post", "/api/godot-camera/status"),
        ("post", "/api/godot-camera/frame"),
        ("get", "/api/godot-camera/control"),
    ],
)
def test_product_api_retires_jpeg_camera_routes(
    client: TestClient,
    method: str,
    path: str,
) -> None:
    # Given: a normal product API application with an authenticated owner.
    csrf_token = _login(client)

    # When: any retired fixed-camera endpoint is requested.
    headers = {"X-CSRF-Token": csrf_token} if method in {"post", "put"} else {}
    response = getattr(client, method)(path, headers=headers)

    # Then: it is absent rather than becoming an implicit JPEG fallback.
    assert response.status_code == 404
