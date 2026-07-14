from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from elfienest.api.app import create_app


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "nest.db")


@pytest.fixture
def client(db_path: str):
    with (
        patch("elfienest.api.app.AuthenticatedWSManager.start"),
        patch("elfienest.api.app.AuthenticatedWSManager.stop"),
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

    console_js = client.get("/static/elfienest-console.js")
    assert console_js.status_code == 200
    assert "/api/auth/setup-status" in console_js.text
    assert "/static/setup.html" in console_js.text


def test_static_index_redirects_to_root(client: TestClient) -> None:
    resp = client.get("/static/index.html", follow_redirects=False)

    assert resp.status_code == 308
    assert resp.headers["location"] == "/"


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
