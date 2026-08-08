"""测试首启向导状态和 draft/install 流程。

使用 tmp_path 隔离 DB，mock WS 网关。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.ollama_platform import OllamaBinding, OllamaProbe
from app.interfaces.api.app import create_app

from ._helpers import create_test_owner


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "nest.db")


@pytest.fixture
def app(db_path: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ELFIE_HOME", str(Path(db_path).parent))
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        yield application


@pytest.fixture
def client(app):
    with TestClient(app, base_url="http://127.0.0.1:8000") as c:
        yield c


class TestSetupStatus:
    def test_legacy_immediate_setup_endpoint_is_removed(
        self, client: TestClient
    ) -> None:
        response = client.get("/api/auth/setup")

        assert response.status_code == 404

    def test_setup_status_empty_db(self, client: TestClient) -> None:
        """空数据库时状态 API 从第一步开始，并公开五步进度。"""
        resp = client.get("/api/auth/setup-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["need_setup"] is True
        assert data["complete"] is False
        assert data["current_step"] == 1
        assert [step["number"] for step in data["steps"]] == [1, 2, 3, 4]
        assert data["steps"][0]["status"] == "current"

    def test_setup_status_with_users(self, client: TestClient, db_path: str) -> None:
        """已有 Owner 不是 Setup 完成：迁移后必须从第二步继续。"""
        create_test_owner(db_path)
        resp = client.get("/api/auth/setup-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["need_setup"] is True
        assert data["current_step"] == 2
        assert data["steps"][0]["status"] == "completed"

    def test_setup_status_marks_stopped_installed_ollama_as_reusable(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.interfaces.api.setup_routes.OllamaPlatformAdapter",
            _StoppedOllamaAdapter,
        )

        response = client.get("/api/auth/setup-status")

        assert response.status_code == 200
        assert response.json()["draft"]["ollama_installed"] is True


class _StoppedOllamaAdapter:
    platform = "darwin"

    def probe(self, binding: OllamaBinding | None) -> OllamaProbe:
        assert binding is not None
        assert binding.launch_target == "/Applications/Ollama.app"
        return OllamaProbe("stopped", binding.api_base)
