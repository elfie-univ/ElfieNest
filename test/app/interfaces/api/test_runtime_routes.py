from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from ai_runtime.usage.observer import (
    FallbackObservation,
    RuntimeEventStatus,
    RuntimeObserver,
    ToolCallObservation,
)
from app.infrastructure.persistence.store import init_db
from app.interfaces.api.app import create_app

from ._helpers import create_test_owner, create_test_user


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "nest.db")


@pytest.fixture
def runtime_observer() -> RuntimeObserver:
    observer = RuntimeObserver()
    observer.record_tool_call(
        ToolCallObservation(
            tool_name="web_search",
            status=RuntimeEventStatus.OK,
            metadata={"query": "ElfieNest"},
        )
    )
    observer.record_fallback(
        FallbackObservation(
            from_model_key="remote_deep",
            from_provider="openai",
            to_model_key="local_fast",
            to_provider="ollama",
            reason="remote unavailable",
        )
    )
    return observer


@pytest.fixture
def client(
    db_path: str,
    runtime_observer: RuntimeObserver,
):
    init_db(db_path)
    create_test_owner(db_path)
    create_test_user(db_path, "alice", "pass123")

    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
        patch(
            "app.interfaces.api.runtime_routes.get_runtime_observer",
            return_value=runtime_observer,
        ),
    ):
        app = create_app(engine=None, db_path=db_path, ws_port=9876)
        with TestClient(app) as test_client:
            yield test_client


def _login(client: TestClient, account_id: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        data={"account_id": account_id, "password": password},
    )
    assert response.status_code == 200
    return {"csrf_token": response.headers.get("X-CSRF-Token", "")}


def test_owner_runtime_status_returns_diagnostic_snapshot(client: TestClient) -> None:
    tokens = _login(client, "owner", "ownerchangeme")

    response = client.get(
        "/api/owner/runtime/status",
        headers={"X-CSRF-Token": tokens["csrf_token"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"status", "observer"}
    assert payload["status"] == "ok"
    assert payload["observer"]["event_count"] == 2
    assert payload["observer"]["last_event"]["subject"] == "local_fast"


def test_non_owner_cannot_read_runtime_status(client: TestClient) -> None:
    tokens = _login(client, "alice", "pass123")

    response = client.get(
        "/api/owner/runtime/status",
        headers={"X-CSRF-Token": tokens["csrf_token"]},
    )

    assert response.status_code == 403
