from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.bootstrap.api import create_app
from app.features.setup import StoredSetupInstallation
from app.orchestration.nest_session import (
    ElfieNestEngine,
    RuntimeConnection,
    SceneManifest,
    SemanticWorldCatalog,
    WorldAnchor,
    WorldConfigured,
    WorldEvent,
    WorldEventName,
    WorldZone,
)
from app.orchestration.setup_installation import (
    CancelSetupInstallationResult,
    SetupInstallationService,
)
from infrastructure.persistence.nest_db.nest_state import SQLiteNestStateAdapter
from infrastructure.persistence.nest_db.store import init_db
from test.app.orchestration.nest_session.fakes import FakeWorldRuntime


class AcceptedCancellation(SetupInstallationService):
    def __init__(self) -> None:
        pass

    def cancel(self, _command: object) -> CancelSetupInstallationResult:
        return CancelSetupInstallationResult(
            StoredSetupInstallation(
                1,
                "in_progress",
                2,
                "cancelled",
                "cancelled",
                20,
                None,
                None,
            )
        )


class _ReadyWorldRuntime(FakeWorldRuntime):
    """Test runtime that returns the semantic readiness events Setup waits for."""

    def __init__(self) -> None:
        super().__init__()
        self.connection = RuntimeConnection("setup-runtime", 1)

    def configure_world(
        self,
        *,
        nest_id: str,
        bed_count: int,
        world_revision: int,
    ) -> str | None:
        command_id = super().configure_world(
            nest_id=nest_id,
            bed_count=bed_count,
            world_revision=world_revision,
        )
        if command_id is None:
            return None
        self.events.extend(
            (
                WorldEvent(
                    event_id=f"{command_id}-manifest",
                    connection=self.connection,
                    world_revision=world_revision,
                    name=WorldEventName.SCENE_MANIFEST,
                    payload=SceneManifest(_catalog(bed_count, world_revision)),
                ),
                WorldEvent(
                    event_id=f"{command_id}-configured",
                    connection=self.connection,
                    world_revision=world_revision,
                    name=WorldEventName.WORLD_CONFIGURED,
                    payload=WorldConfigured(True, True),
                ),
            )
        )
        return command_id


def _application_with_engine(tmp_path: Path):
    db_path = init_db(str(tmp_path / "nest.db"))
    state_store = SQLiteNestStateAdapter(db_path)
    engine = ElfieNestEngine(_ReadyWorldRuntime(), state_store=state_store)
    return create_app(engine=engine, db_path=db_path), engine, state_store


def _catalog(bed_count: int, revision: int) -> SemanticWorldCatalog:
    return SemanticWorldCatalog(
        nest_id="local-nest",
        revision=revision,
        zones=(
            WorldZone(
                zone_id="dorm-01",
                label="Dorm",
                order=0,
                anchors=tuple(
                    WorldAnchor(
                        anchor_id=f"dorm-01/bed-{index:02d}",
                        kind="bed",
                        label=f"Bed {index}",
                        order=index - 1,
                        active=True,
                    )
                    for index in range(1, bed_count + 1)
                ),
            ),
        ),
    )


def test_real_setup_chain_creates_owner_session_and_nest_once(tmp_path: Path) -> None:
    application, engine, state_store = _application_with_engine(tmp_path)
    with TestClient(application) as client:
        status = client.get("/api/v1/setup/status")
        csrf = status.headers["X-CSRF-Token"]
        headers = {"X-CSRF-Token": csrf}
        owner_saved = client.put(
            "/api/v1/setup/draft/owner",
            headers=headers,
            json={
                "account_id": "owner",
                "display_name": "Owner",
                "password": "owner-secret",
                "confirm_password": "owner-secret",
            },
        )
        assert owner_saved.status_code == 200
        assert owner_saved.cookies.get("session_token")
        assert client.get("/api/v1/me").status_code == 200
        skipped = client.put(
            "/api/v1/setup/draft/remote",
            headers=headers,
            json={"configured": False, "connection_id": None},
        )
        assert skipped.status_code == 200
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
            engine.tick_once(0.0)
            time.sleep(0.01)
            current = client.get("/api/v1/setup/status").json()

        assert current["complete"] is True
        assert current["draft"]["bed_count"] == 12
        session = client.cookies.get("session_token")
        assert session is not None
        principal = application.state.accounts.authenticate_session(session)
        assert principal is not None
        assert principal.role == "owner"
        assert (
            application.state.nest_management.get_rooms(principal)[0].desired_bed_count
            == 12
        )
        for _ in range(3):
            engine.tick_once(0.0)
        assert state_store.load_snapshot().desired_bed_count == 12
        restarted = ElfieNestEngine(_ReadyWorldRuntime(), state_store=state_store)
        assert restarted.nest.desired_bed_count == 12


def test_real_setup_chain_skips_remote_food_and_uses_default_twelve_beds(
    tmp_path: Path,
) -> None:
    application, engine, state_store = _application_with_engine(tmp_path)
    with TestClient(application) as client:
        status = client.get("/api/v1/setup/status")
        headers = {"X-CSRF-Token": status.headers["X-CSRF-Token"]}
        owner_saved = client.put(
            "/api/v1/setup/draft/owner",
            headers=headers,
            json={
                "account_id": "owner",
                "display_name": "Owner",
                "password": "owner-secret",
                "confirm_password": "owner-secret",
            },
        )
        assert owner_saved.status_code == 200

        skipped = client.put(
            "/api/v1/setup/draft/remote",
            headers=headers,
            json={"configured": False, "connection_id": None},
        )
        assert skipped.status_code == 200
        assert skipped.json()["draft"]["remote_configured"] is False
        assert skipped.json()["draft"]["remote_skipped"] is True
        assert skipped.json()["draft"]["bed_count"] == 12

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
            engine.tick_once(0.0)
            time.sleep(0.01)
            current = client.get("/api/v1/setup/status").json()

        assert current["complete"] is True
        assert current["draft"]["bed_count"] == 12
        session = client.cookies.get("session_token")
        assert session is not None
        principal = application.state.accounts.authenticate_session(session)
        assert principal is not None
        assert (
            application.state.nest_management.get_rooms(principal)[0].desired_bed_count
            == 12
        )
        for _ in range(3):
            engine.tick_once(0.0)
        assert state_store.load_snapshot().desired_bed_count == 12


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


def test_setup_status_renews_setup_lease_and_disables_browser_cache(
    tmp_path: Path,
) -> None:
    application, _, _ = _application_with_engine(tmp_path)
    with TestClient(application) as client:
        initial = client.get("/api/v1/setup/status")
        renewed = client.get("/api/v1/setup/status")

    assert renewed.status_code == 200
    assert (
        renewed.headers["Cache-Control"]
        == "no-store, no-cache, must-revalidate, max-age=0"
    )
    assert renewed.headers["X-CSRF-Token"] == renewed.json()["csrf_token"]
    assert "Max-Age=900" in renewed.headers["set-cookie"]
    assert renewed.json()["csrf_token"] == initial.json()["csrf_token"]


def test_setup_status_recovers_expired_cookie_before_owner_write(
    tmp_path: Path,
) -> None:
    application, _, _ = _application_with_engine(tmp_path)
    with TestClient(application) as client:
        initial = client.get("/api/v1/setup/status")
        old_csrf = initial.headers["X-CSRF-Token"]
        client.cookies.delete("setup_token")
        rejected = client.put(
            "/api/v1/setup/draft/owner",
            headers={"X-CSRF-Token": old_csrf},
            json={
                "account_id": "owner",
                "display_name": "Owner",
                "password": "owner-secret",
                "confirm_password": "owner-secret",
            },
        )
        refreshed = client.get("/api/v1/setup/status")
        recovered = client.put(
            "/api/v1/setup/draft/owner",
            headers={"X-CSRF-Token": refreshed.headers["X-CSRF-Token"]},
            json={
                "account_id": "owner",
                "display_name": "Owner",
                "password": "owner-secret",
                "confirm_password": "owner-secret",
            },
        )

    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "csrf_rejected"
    assert refreshed.status_code == 200
    assert refreshed.cookies.get("setup_token")
    assert recovered.status_code == 200


def test_setup_status_replaces_empty_cookie_before_owner_write(
    tmp_path: Path,
) -> None:
    application, _, _ = _application_with_engine(tmp_path)
    with TestClient(application) as client:
        client.get("/api/v1/setup/status")
        client.cookies.set("setup_token", "")
        refreshed = client.get("/api/v1/setup/status")
        response = client.put(
            "/api/v1/setup/draft/owner",
            headers={"X-CSRF-Token": refreshed.headers["X-CSRF-Token"]},
            json={
                "account_id": "owner",
                "display_name": "Owner",
                "password": "owner-secret",
                "confirm_password": "owner-secret",
            },
        )

    assert refreshed.status_code == 200
    assert refreshed.cookies.get("setup_token")
    assert response.status_code == 200


def test_setup_cancel_uses_setup_csrf_through_the_production_middleware(
    tmp_path: Path,
) -> None:
    application, _, _ = _application_with_engine(tmp_path)
    application.state.setup_installation = AcceptedCancellation()
    with TestClient(application) as client:
        status = client.get("/api/v1/setup/status")
        response = client.post(
            "/api/v1/setup/installation/cancel",
            headers={"X-CSRF-Token": status.headers["X-CSRF-Token"]},
        )

    assert response.status_code == 200
    assert response.headers["X-CSRF-Token"] == response.json()["csrf_token"]
