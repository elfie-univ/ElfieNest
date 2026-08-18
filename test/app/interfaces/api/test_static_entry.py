"""React Web entry and retired static-console contract tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import create_app


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
    application = create_app(
        engine=None,
        db_path=str(tmp_path / "nest.db"),
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


def test_legacy_godot_web_status_resource_is_retired(client: TestClient) -> None:
    response = client.get("/api/godot-web/status")

    assert response.status_code == 404


def test_health_does_not_run_full_godot_bundle_integrity_check(
    tmp_path: Path,
) -> None:
    # Given: full Godot bundle verification is too expensive for a readiness probe.
    with (
        patch(
            "infrastructure.godot.gateway.bundle.inspect_godot_web_bundle"
        ) as inspect_bundle,
        patch(
            "app.bootstrap.api.godot_web_bundle_present",
            return_value=False,
        ),
    ):
        application = create_app(
            engine=None,
            db_path=str(tmp_path / "nest.db"),
            web_build_dir=tmp_path / "missing-web-build",
        )
        with TestClient(
            application,
            base_url="http://127.0.0.1:8000",
        ) as test_client:
            response = test_client.get("/api/health")

    # Then: health remains a cheap readiness probe with one strict response shape.
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "engine_ready": False,
        "godot_web_ready": False,
        "godot_runtime_ready": False,
        "instance_id": "unavailable",
        "generation": 0,
    }
    inspect_bundle.assert_not_called()
