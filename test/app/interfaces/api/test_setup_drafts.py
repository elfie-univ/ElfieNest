"""HTTP contract for pre-Owner Setup draft writes."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.interfaces.api.app import create_app


def _app(db_path: str):
    return create_app(engine=None, db_path=db_path, ws_port=9876)


def test_setup_status_issues_local_setup_cookie_and_csrf(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    with patch("app.interfaces.api.app.AuthenticatedWSManager.start"), patch(
        "app.interfaces.api.app.AuthenticatedWSManager.stop"
    ):
        with TestClient(_app(db_path), base_url="http://127.0.0.1:8000") as client:
            response = client.get("/api/auth/setup-status")

    assert response.status_code == 200
    assert "setup_token" in response.cookies
    assert "x-csrf-token" in response.headers
    assert response.json()["draft"]["password_configured"] is False


def test_setup_draft_writes_require_setup_csrf_and_do_not_create_owner(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "nest.db")
    with patch("app.interfaces.api.app.AuthenticatedWSManager.start"), patch(
        "app.interfaces.api.app.AuthenticatedWSManager.stop"
    ):
        with TestClient(_app(db_path), base_url="http://127.0.0.1:8000") as client:
            status = client.get("/api/auth/setup-status")
            missing_csrf = client.put(
                "/api/auth/setup/draft/owner",
                json={
                    "account_id": "owner",
                    "display_name": "First Owner",
                    "password": "securePass123",
                    "confirm_password": "securePass123",
                },
            )
            saved_owner = client.put(
                "/api/auth/setup/draft/owner",
                headers={"X-CSRF-Token": status.headers["X-CSRF-Token"]},
                json={
                    "account_id": "owner",
                    "display_name": "First Owner",
                    "password": "securePass123",
                    "confirm_password": "securePass123",
                },
            )
            saved_offline = client.put(
                "/api/auth/setup/draft/offline",
                headers={"X-CSRF-Token": status.headers["X-CSRF-Token"]},
                json={"use_local_ollama": True, "model_id": "qwen2.5:0.5b"},
            )
            saved_nest = client.put(
                "/api/auth/setup/draft/nest",
                headers={"X-CSRF-Token": status.headers["X-CSRF-Token"]},
                json={"bed_count": 8},
            )
            refreshed = client.get("/api/auth/setup-status")

    assert missing_csrf.status_code == 403
    assert saved_owner.status_code == 200, saved_owner.text
    assert saved_offline.status_code == 200, saved_offline.text
    assert saved_nest.status_code == 200, saved_nest.text
    draft = refreshed.json()["draft"]
    assert draft["owner_account_id"] == "owner"
    assert draft["display_name"] == "First Owner"
    assert draft["password_configured"] is True
    assert draft["use_local_ollama"] is True
    assert draft["model_id"] == "qwen2.5:0.5b"
    assert draft["bed_count"] == 8
    assert "password_hash" not in refreshed.json()

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone() == (0,)


def test_setup_draft_rejects_lan_and_fake_csrf(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    with patch("app.interfaces.api.app.AuthenticatedWSManager.start"), patch(
        "app.interfaces.api.app.AuthenticatedWSManager.stop"
    ):
        application = _app(db_path)
        with TestClient(
            application,
            base_url="http://192.168.1.8:8000",
            client=("192.168.1.30", 50000),
        ) as client:
            status = client.get("/api/auth/setup-status")
            response = client.put(
                "/api/auth/setup/draft/owner",
                headers={"X-CSRF-Token": status.headers["X-CSRF-Token"]},
                json={"account_id": "owner"},
            )

    assert response.status_code == 403
