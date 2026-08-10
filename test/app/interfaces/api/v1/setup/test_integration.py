from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.bootstrap.api import create_app


def test_real_setup_chain_creates_owner_session_and_nest_once(tmp_path: Path) -> None:
    application = create_app(db_path=str(tmp_path / "nest.db"))
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
        TestClient(application) as client,
    ):
        status = client.get("/api/v1/setup/status")
        csrf = status.headers["X-CSRF-Token"]
        headers = {"X-CSRF-Token": csrf}
        assert (
            client.put(
                "/api/v1/setup/draft/owner",
                headers=headers,
                json={
                    "account_id": "owner",
                    "display_name": "Owner",
                    "password": "owner-secret",
                    "confirm_password": "owner-secret",
                },
            ).status_code
            == 200
        )
        assert (
            client.put(
                "/api/v1/setup/draft/offline",
                headers=headers,
                json={"use_local_ollama": False, "model_id": None},
            ).status_code
            == 200
        )
        assert (
            client.put(
                "/api/v1/setup/draft/nest",
                headers=headers,
                json={"bed_count": 8},
            ).status_code
            == 200
        )

        accepted = client.post(
            "/api/v1/setup/installation",
            headers=headers,
            json={"confirmed": True},
        )
        assert accepted.status_code in {200, 202}
        assert accepted.cookies.get("session_token")

        deadline = time.monotonic() + 2.0
        current = accepted.json()
        while (
            current["install"]["state"] != "completed" and time.monotonic() < deadline
        ):
            time.sleep(0.01)
            current = client.get("/api/v1/setup/status").json()

        assert current["complete"] is True
        assert current["draft"]["bed_count"] == 8
        session = client.cookies.get("session_token")
        assert session is not None
        principal = application.state.accounts.authenticate_session(session)
        assert principal is not None
        assert principal.role == "owner"
        assert (
            application.state.nest_management.get_rooms(principal)[0].desired_bed_count
            == 8
        )
