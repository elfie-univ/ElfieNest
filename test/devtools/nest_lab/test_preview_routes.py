from subprocess import CalledProcessError
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from devtools.elfie_lab.app import create_unified_app
from devtools.nest_lab.app import create_app


@pytest.fixture(autouse=True)
def no_frontend_build(monkeypatch):
    monkeypatch.setattr("devtools.nest_lab.app.mount_static_surfaces", lambda _: True)
    monkeypatch.setattr("devtools.elfie_lab.app.mount_static_surfaces", lambda _: None)


@pytest.mark.parametrize("factory", [create_app, create_unified_app])
def test_both_lab_hosts_prepare_the_same_preview_pair(tmp_path, monkeypatch, factory):
    prepare = Mock()
    monkeypatch.setattr("devtools.nest_lab.routes.ensure_preview_bundle", prepare)
    client = TestClient(factory(tmp_path), base_url="http://127.0.0.1")
    assert client.post("/api/preview/prepare").json() == {"ready": True}
    prepare.assert_called_once_with()


@pytest.mark.parametrize(
    "failure", [RuntimeError("source changed"), CalledProcessError(1, "build")]
)
def test_failed_update_is_reported_without_claiming_readiness(
    tmp_path, monkeypatch, failure
):
    monkeypatch.setattr(
        "devtools.nest_lab.routes.ensure_preview_bundle", Mock(side_effect=failure)
    )
    client = TestClient(create_app(tmp_path), base_url="http://127.0.0.1")
    response = client.post("/api/preview/prepare")
    assert response.status_code == 503
    assert "保留上一套" in response.json()["detail"]
