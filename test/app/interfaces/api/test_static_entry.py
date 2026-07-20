from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.interfaces.api.app import create_app


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "nest.db")


@pytest.fixture
def client(db_path: str):
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        with TestClient(application) as c:
            yield c


def test_root_serves_console_without_static_redirect(client: TestClient) -> None:
    resp = client.get("/", follow_redirects=False)

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "<title>ElfieNest 控制台</title>" in resp.text
    assert "Runtime 三层配置" in resp.text
    assert "第二层：Agent 基础工具" in resp.text
    assert "自动更新粮食策略" in resp.text
    assert client.get("/api/ws-config").json() == {"port": 9876}
    assert 'id="login-form"' in resp.text
    assert '<script src="/static/elfienest-console.js?v=21"></script>' in resp.text

    console_js = client.get("/static/elfienest-console.js")
    assert console_js.status_code == 200
    assert "/api/auth/setup-status" in console_js.text
    assert "/static/setup.html" in console_js.text
    assert "currentUser?.session_token" not in console_js.text
    assert ":8766`" not in console_js.text


def test_capacity_inputs_and_payloads_are_capped_at_thirty_two(
    client: TestClient,
) -> None:
    index = client.get("/")
    console_js = client.get("/static/elfienest-console.js")

    assert 'id="room-bed-count" type="number" min="4" max="32"' in index.text
    assert (
        'name="max_elfies_per_user" type="number" min="1" max="32"' in console_js.text
    )
    assert (
        'name="max_elfies_per_room" type="number" min="1" max="32"' in console_js.text
    )
    assert "Math.min(32, maxPerUser)" in console_js.text
    assert "Math.min(32, Number(maxRoom))" in console_js.text
    assert "Math.min(32, Number(bedCountInput?.value || 4))" in console_js.text


def test_room_camera_uses_live_godot_frames_and_reported_views(
    client: TestClient,
) -> None:
    index = client.get("/")
    console_js = client.get("/static/elfienest-console.js")

    assert 'id="room-camera-thumbnail"' in index.text
    assert 'id="room-camera-live-image"' in index.text
    assert 'id="room-camera-view-strip" role="listbox"' in index.text
    assert 'id="godot-web-runtime"' in index.text
    assert "/api/camera/frame.jpg" in console_js.text
    assert 'fetchJson("/api/godot-web/status")' in console_js.text
    assert "elfienest:godot-web-ready" in console_js.text
    assert 'fetchJson("/api/camera/status")' in console_js.text
    assert 'fetchJson("/api/camera/view"' in console_js.text
    assert "renderDormFloorplan(room, beds)" in console_js.text
    assert "room-camera-plan" not in index.text


def test_godot_web_status_reports_missing_bundle(client: TestClient) -> None:
    missing_bundle = SimpleNamespace(
        ready=False,
        entry_url="/runtime/godot/elfienest.html",
        missing=(".html", ".js", ".wasm", ".pck", "build-manifest.json"),
        manifest={},
    )
    with patch(
        "app.interfaces.api.app.inspect_godot_web_bundle",
        return_value=missing_bundle,
    ):
        status = client.get("/api/godot-web/status")
        health = client.get("/api/health")

    assert status.status_code == 200
    assert status.json()["ready"] is False
    assert status.json()["entry_url"] == "/runtime/godot/elfienest.html"
    assert ".wasm" in status.json()["missing"]
    assert health.json()["godot_web_ready"] is False


def test_room_layout_change_requires_confirmation_and_exposes_rebuild_state(
    client: TestClient,
) -> None:
    index = client.get("/")
    console_js = client.get("/static/elfienest-console.js")
    console_css = client.get("/static/elfienest-console.css")

    assert 'id="room-layout-confirm-modal"' in index.text
    assert 'id="room-layout-confirm-submit"' in index.text
    assert "openCenterModal(roomLayoutConfirmModal)" in console_js.text
    assert "confirmRoomLayoutChange" in console_js.text
    assert 'bedCountInput.value = String(rooms[0]?.beds?.length || 4)' in console_js.text
    assert "waitForGodotLayout" in console_js.text
    assert 'roomLayoutStatusOverride = "正在重建"' in console_js.text
    assert ".is-loading::before" in console_css.text


def test_static_index_redirects_to_root(client: TestClient) -> None:
    resp = client.get("/static/index.html", follow_redirects=False)

    assert resp.status_code == 308
    assert resp.headers["location"] == "/"


def test_obsolete_login_page_is_removed_and_setup_targets_root(
    client: TestClient,
) -> None:
    obsolete_login = client.get("/static/login.html", follow_redirects=False)
    setup = client.get("/static/setup.html")

    assert obsolete_login.status_code == 404
    assert setup.status_code == 200
    assert "/static/login.html" not in setup.text
    assert "window.location.href = '/';" in setup.text


def test_route_parameter_annotations_are_python39_compatible(
    client: TestClient,
) -> None:
    """FastAPI 会在启动时重新解析字符串注解，不能使用 3.10 的 ``|``。"""
    incompatible = []
    for route in client.app.routes:
        if not isinstance(route, APIRoute):
            continue
        for parameter in inspect.signature(route.endpoint).parameters.values():
            annotation = parameter.annotation
            if isinstance(annotation, str) and "|" in annotation:
                incompatible.append(f"{route.path}:{parameter.name}={annotation}")

    assert incompatible == []
