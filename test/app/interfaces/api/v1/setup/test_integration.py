from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.bootstrap.api import create_app
from app.orchestration.nest_session import ElfieNestEngine
from infrastructure.persistence.nest_db.nest_state import SQLiteNestStateAdapter
from infrastructure.persistence.nest_db.store import init_db
from test.app.orchestration.nest_session.fakes import FakeWorldRuntime


def _application_with_engine(tmp_path: Path):
    db_path = init_db(str(tmp_path / "nest.db"))
    state_store = SQLiteNestStateAdapter(db_path)
    engine = ElfieNestEngine(FakeWorldRuntime(), state_store=state_store)
    return create_app(engine=engine, db_path=db_path), engine, state_store


def test_real_setup_chain_creates_owner_session_and_nest_once(tmp_path: Path) -> None:
    application, engine, state_store = _application_with_engine(tmp_path)
    with TestClient(application) as client:
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
        for _ in range(3):
            engine.tick_once(1.0)
        assert state_store.load_snapshot().desired_bed_count == 8
        restarted = ElfieNestEngine(FakeWorldRuntime(), state_store=state_store)
        assert restarted.nest.desired_bed_count == 8


def test_real_setup_chain_replaces_stale_session_cookie_before_writing_owner(
    tmp_path: Path,
) -> None:
    application, _, _ = _application_with_engine(tmp_path)
    with TestClient(application) as client:
        client.cookies.set("session_token", "stale-session-token")
        status = client.get("/api/v1/setup/status")
        csrf = status.headers["X-CSRF-Token"]
        response = client.put(
            "/api/v1/setup/draft/owner",
            headers={"X-CSRF-Token": csrf},
            json={
                "account_id": "owner",
                "display_name": "Owner",
                "password": "owner-secret",
                "confirm_password": "owner-secret",
            },
        )

    assert response.status_code == 200
