from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.features.accounts import AccountPrincipal, AccountsService
from app.features.elfies import ElfiesService
from app.infrastructure.persistence.store import init_db
from app.interfaces.api.v1.auth import get_current_user
from app.interfaces.api.v1.observer import router
from app.orchestration.observer import (
    ObserverEntityRecord,
    ObserverFacade,
    ObserverWorldIntent,
)
from test.app.interfaces.api._helpers import create_test_owner


class FixedClock:
    def now(self) -> float:
        return 10.0


class FixedCapabilities:
    def issue(self) -> str:
        return "observer-capability"


class MemoryWorld:
    def __init__(self) -> None:
        self.intents: list[ObserverWorldIntent] = []

    def list_entities(self) -> tuple[ObserverEntityRecord, ...]:
        return (
            ObserverEntityRecord(
                entity_id="fox-1",
                room_id="local-nest",
                zone_id=None,
                posture="awake",
                active=True,
                active_command_id=None,
                species_id="fox",
                appearance=(),
                home_anchor_id=None,
            ),
        )

    def submit_intent(self, intent: ObserverWorldIntent) -> None:
        self.intents.append(intent)


def _application() -> tuple[FastAPI, MemoryWorld]:
    accounts = MagicMock(spec=AccountsService)
    accounts.session_ttl_seconds.return_value = 60
    elfies = MagicMock(spec=ElfiesService)
    elfies.list_visible.return_value = (
        SimpleNamespace(profile=SimpleNamespace(elfie_id="fox-1")),
    )
    world = MemoryWorld()
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[get_current_user] = lambda: AccountPrincipal(
        7, "alice", "user", "chat"
    )
    application.state.observer = ObserverFacade(
        accounts=accounts,
        elfies=elfies,
        world=world,
        clock=FixedClock(),
        capabilities=FixedCapabilities(),
    )
    return application, world


def test_versioned_routes_return_strict_capability_snapshot_and_intent_result() -> None:
    application, world = _application()
    with TestClient(application) as client:
        client.cookies.set("session_token", "login-token")
        opened = client.post(
            "/api/v1/observer/sessions",
            json={
                "protocol": 3,
                "role": "observer",
                "subscription": {"kind": "elfie", "elfie_id": "fox-1"},
            },
        )
        capability = opened.json()["capability"]
        headers = {"X-ElfieNest-Observer-Capability": capability}
        frame = client.get("/api/v1/observer/frames", headers=headers)
        accepted = client.post(
            "/api/v1/observer/intents",
            headers=headers,
            json={
                "kind": "request_interaction",
                "actor_id": "fox-1",
                "interaction": "greet",
            },
        )

    assert opened.status_code == 201
    assert set(opened.json()) == {"capability"}
    assert frame.status_code == 200
    assert frame.json() == {
        "protocol": 3,
        "kind": "snapshot",
        "generation": 1,
        "sequence": 1,
        "scope": {"kind": "elfie", "room_id": None, "elfie_id": "fox-1"},
        "entities": {
            "fox-1": {
                "room_id": "local-nest",
                "zone_id": None,
                "posture": "awake",
                "active": True,
                "active_command_id": None,
                "species_id": "fox",
                "appearance": {},
                "home_anchor_id": None,
            }
        },
        "entity_revisions": {"fox-1": 1},
    }
    assert accepted.status_code == 202
    assert accepted.json() == {"detail": "observer intent accepted"}
    assert world.intents == [ObserverWorldIntent(actor_id="fox-1", interaction="greet")]


def test_routes_reject_authority_fields_and_use_stable_error_envelope() -> None:
    application, _world = _application()
    with TestClient(application) as client:
        rejected_payload = client.post(
            "/api/v1/observer/sessions",
            json={
                "protocol": 3,
                "role": "observer",
                "subscription": {"kind": "room", "room_id": "local-nest"},
                "nonce": "authority-only",
            },
        )
        forbidden = client.get(
            "/api/v1/observer/frames",
            headers={"X-ElfieNest-Observer-Capability": "unknown"},
        )

    assert rejected_payload.status_code == 422
    assert forbidden.status_code == 403
    assert forbidden.json() == {
        "error": {
            "code": "observer_forbidden",
            "message": "invalid observer capability",
            "details": {},
        }
    }


def test_production_router_requires_csrf_and_logout_revokes_capability(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_test_owner(db_path)
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=19876)
        with TestClient(application) as client:
            login = client.post(
                "/api/v1/auth/login",
                data={"account_id": "owner", "password": "ownerchangeme"},
            )
            csrf = login.headers["X-CSRF-Token"]
            payload = {
                "protocol": 3,
                "role": "observer",
                "subscription": {"kind": "room", "room_id": "local-nest"},
            }
            missing_csrf = client.post("/api/v1/observer/sessions", json=payload)
            opened = client.post(
                "/api/v1/observer/sessions",
                json=payload,
                headers={"X-CSRF-Token": csrf},
            )
            capability = opened.json()["capability"]
            logout = client.post(
                "/api/v1/auth/logout",
                headers={"X-CSRF-Token": csrf},
            )
            second_login = client.post(
                "/api/v1/auth/login",
                data={"account_id": "owner", "password": "ownerchangeme"},
            )
            replay = client.get(
                "/api/v1/observer/frames",
                headers={
                    "X-ElfieNest-Observer-Capability": capability,
                    "X-CSRF-Token": second_login.headers["X-CSRF-Token"],
                },
            )

    assert missing_csrf.status_code == 403
    assert opened.status_code == 201
    assert logout.status_code == 200
    assert replay.status_code == 403
