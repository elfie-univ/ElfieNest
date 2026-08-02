"""Boundary tests for first-owner Setup request validation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.interfaces.api.app import create_app
from app.interfaces.api.setup_models import SetupRequest


def test_setup_request_rejects_whitespace_only_password() -> None:
    """Given a blank-after-trim password, Setup rejects the request boundary."""
    with pytest.raises(ValidationError):
        SetupRequest(account_id="owner", password="      ")


def test_setup_endpoint_rejects_whitespace_only_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given an empty fresh root, the HTTP Setup endpoint returns 422 for blank password."""
    db_path = str(tmp_path / "nest.db")
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        with TestClient(application, base_url="http://127.0.0.1:8000") as client:
            response = client.post(
                "/api/auth/setup",
                json={"account_id": "owner", "password": "      "},
            )

    assert response.status_code == 422
