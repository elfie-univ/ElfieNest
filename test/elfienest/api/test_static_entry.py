from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
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


def test_static_index_redirects_to_root(client: TestClient) -> None:
    resp = client.get("/static/index.html", follow_redirects=False)

    assert resp.status_code == 308
    assert resp.headers["location"] == "/"
