"""HTTP contract for the one-confirmation locked Setup install."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.infrastructure.persistence.setup_install_repository import (
    SetupInstallRepository,
)
from app.interfaces.api.app import create_app


def _draft(client: TestClient, csrf: str) -> None:
    headers = {"X-CSRF-Token": csrf}
    owner = client.put(
        "/api/auth/setup/draft/owner",
        headers=headers,
        json={
            "account_id": "owner",
            "display_name": "Owner",
            "password": "securePass123",
            "confirm_password": "securePass123",
        },
    )
    offline = client.put(
        "/api/auth/setup/draft/offline",
        headers=headers,
        json={"use_local_ollama": False},
    )
    nest = client.put(
        "/api/auth/setup/draft/nest",
        headers=headers,
        json={"bed_count": 4},
    )
    assert owner.status_code == 200, owner.text
    assert offline.status_code == 200, offline.text
    assert nest.status_code == 200, nest.text


def _application(tmp_path: Path):
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
    ):
        return create_app(
            engine=None,
            db_path=str(tmp_path / "nest.db"),
            ws_port=9876,
        )


def test_install_confirm_creates_owner_locks_draft_and_runs_one_worker(
    tmp_path: Path,
) -> None:
    application = _application(tmp_path)

    def worker_factory(db_path: str):
        def worker() -> None:
            repository = SetupInstallRepository(db_path)
            for phase, progress in ((2, 30), (3, 50), (4, 70), (5, 90)):
                repository.update(
                    phase=phase,
                    action_key=f"phase.{phase}",
                    progress=progress,
                )
                repository.complete_phase(phase=phase)

        return worker

    application.state.setup_install_worker_factory = worker_factory
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
        TestClient(application, base_url="http://127.0.0.1:8000") as client,
    ):
        status = client.get("/api/auth/setup-status")
        csrf = status.headers["X-CSRF-Token"]
        _draft(client, csrf)

        confirmed = client.post(
            "/api/auth/setup/install",
            headers={"X-CSRF-Token": csrf},
            json={"confirmed": True},
        )
        assert confirmed.status_code == 202, confirmed.text
        assert "session_token" in confirmed.cookies
        owner_csrf = confirmed.headers["X-CSRF-Token"]

        assert application.state.setup_install_jobs.join(
            str(tmp_path / "nest.db"), timeout=2.0
        )
        repeated = client.post(
            "/api/auth/setup/install",
            headers={"X-CSRF-Token": owner_csrf},
            json={"confirmed": True},
        )

    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["complete"] is True
    assert (
        SetupInstallRepository(str(tmp_path / "nest.db")).get_draft().locked_at
        is not None
    )


def test_failed_install_can_retry_without_unlocking_or_duplicate_owner(
    tmp_path: Path,
) -> None:
    application = _application(tmp_path)
    attempts = 0

    def worker_factory(db_path: str):
        def worker() -> None:
            nonlocal attempts
            attempts += 1
            repository = SetupInstallRepository(db_path)
            repository.update(phase=2, action_key="ollama.start", progress=25)
            if attempts == 1:
                raise RuntimeError("first attempt failed")
            for phase in (2, 3, 4, 5):
                repository.update(
                    phase=phase,
                    action_key=f"phase.{phase}",
                    progress={2: 25, 3: 45, 4: 65, 5: 85}[phase],
                )
                repository.complete_phase(phase=phase)

        return worker

    application.state.setup_install_worker_factory = worker_factory
    db_path = str(tmp_path / "nest.db")
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
        TestClient(application, base_url="http://127.0.0.1:8000") as client,
    ):
        status = client.get("/api/auth/setup-status")
        _draft(client, status.headers["X-CSRF-Token"])
        confirmed = client.post(
            "/api/auth/setup/install",
            headers={"X-CSRF-Token": status.headers["X-CSRF-Token"]},
            json={"confirmed": True},
        )
        assert confirmed.status_code == 202, confirmed.text
        assert application.state.setup_install_jobs.join(db_path, timeout=2.0)

        retry = client.post(
            "/api/auth/setup/install",
            headers={"X-CSRF-Token": confirmed.headers["X-CSRF-Token"]},
            json={"confirmed": True},
        )
        assert retry.status_code in {200, 202}, retry.text
        assert application.state.setup_install_jobs.join(db_path, timeout=2.0)

    assert attempts == 2
    assert SetupInstallRepository(db_path).get().task_status == "completed"


def test_install_confirm_uses_setup_csrf_with_stale_session_cookie(
    tmp_path: Path,
) -> None:
    """A stale browser session must not switch pre-Owner Setup to session CSRF."""
    application = _application(tmp_path)

    def worker_factory(db_path: str):
        def worker() -> None:
            SetupInstallRepository(db_path).complete_phase(phase=5)

        return worker

    application.state.setup_install_worker_factory = worker_factory
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
        TestClient(application, base_url="http://127.0.0.1:8000") as client,
    ):
        status = client.get("/api/auth/setup-status")
        csrf = status.headers["X-CSRF-Token"]
        _draft(client, csrf)

        confirmed = client.post(
            "/api/auth/setup/install",
            headers={"X-CSRF-Token": csrf},
            cookies={"session_token": "stale-session-from-previous-run"},
            json={"confirmed": True},
        )

    assert confirmed.status_code == 202, confirmed.text
