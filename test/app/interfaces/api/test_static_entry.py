"""React Web entry and retired static-console contract tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.interfaces.api.app import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    build_dir = tmp_path / "build" / "web"
    assets = build_dir / "assets"
    assets.mkdir(parents=True)
    (build_dir / "index.html").write_text("react-shell", encoding="utf-8")
    (assets / "app.js").write_text("app", encoding="utf-8")
    (build_dir / "manifest.json").write_text(
        '{"index.html": {"file": "assets/app.js"}}', encoding="utf-8"
    )
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
    ):
        application = create_app(
            engine=None,
            db_path=str(tmp_path / "nest.db"),
            ws_port=9876,
            web_build_dir=build_dir,
        )
        with TestClient(application, base_url="http://127.0.0.1:8000") as test_client:
            yield test_client


def test_product_static_console_routes_are_retired(client: TestClient) -> None:
    # Given: the generated React application is the only product shell.
    # When: an old-console URL is requested.
    # Then: it is not mounted or redirected as a compatibility surface.
    response = client.get("/static/index.html", follow_redirects=False)

    assert response.status_code == 404


def test_godot_web_status_reports_missing_bundle(client: TestClient) -> None:
    missing_bundle = SimpleNamespace(
        ready=False,
        entry_url="/runtime/godot/elfienest.html",
        missing=(".html", ".js", ".wasm", ".pck", "build-manifest.json"),
        manifest={},
        integrity_errors=(),
    )
    with (
        patch(
            "app.interfaces.api.app.inspect_godot_web_bundle",
            return_value=missing_bundle,
        ),
        patch(
            "app.interfaces.api.app.godot_web_bundle_present",
            return_value=False,
        ),
    ):
        status = client.get("/api/godot-web/status")
        health = client.get("/api/health")

    assert status.status_code == 200
    assert status.json()["ready"] is False
    assert ".wasm" in status.json()["missing"]
    assert health.json()["godot_web_ready"] is False


def test_health_does_not_run_full_godot_bundle_integrity_check(
    client: TestClient,
) -> None:
    # Given: full Godot bundle verification is too expensive for a readiness probe.
    with patch(
        "app.interfaces.api.app.inspect_godot_web_bundle",
        side_effect=AssertionError("health must not hash the Godot bundle"),
    ):
        # When: the lifecycle supervisor polls the public health endpoint.
        response = client.get("/api/health")

    # Then: health remains a cheap probe and leaves integrity checks to the status route.
    assert response.status_code == 200
