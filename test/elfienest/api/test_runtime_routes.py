import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from elfienest.api.app import create_app
from elfienest.persistence.store import init_db
from runtime.usage.observer import (
    RuntimeEventStatus,
    RuntimeObserver,
    ToolCallObservation,
)
from runtime.usage.token_tracker import TokenTracker

from ._helpers import create_test_admin, create_test_user


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "nest.db")


@pytest.fixture
def runtime_config_path(tmp_path: Path) -> Path:
    path = tmp_path / "runtime" / "runtime_config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "providers": {
                    "ollama": {
                        "api_base": "http://localhost:11434",
                        "api_mode": "ollama",
                    },
                    "deepseek": {
                        "api_base": "https://api.deepseek.com/v1",
                        "api_key": "configured",
                        "api_mode": "chat_completions",
                    },
                },
                "models": {
                    "openai/gpt-4o-mini": {"visible": False, "cost_tier": 2}
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


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
    return observer


@pytest.fixture
def token_tracker() -> TokenTracker:
    tracker = TokenTracker()
    tracker.record("deepseek", {"prompt_tokens": 10, "completion_tokens": 5})
    return tracker


@pytest.fixture
def client(
    db_path: str,
    runtime_config_path: Path,
    runtime_observer: RuntimeObserver,
    token_tracker: TokenTracker,
):
    init_db(db_path)
    create_test_admin(db_path)
    create_test_user(db_path, "alice", "pass123")

    with (
        patch("elfienest.api.app.AuthenticatedWSManager.start"),
        patch("elfienest.api.app.AuthenticatedWSManager.stop"),
        patch("elfienest.api.runtime_routes._RUNTIME_CONFIG_PATH", runtime_config_path),
        patch("elfienest.api.runtime_routes.get_runtime_observer", return_value=runtime_observer),
        patch("elfienest.api.runtime_routes.get_token_tracker", return_value=token_tracker),
    ):
        app = create_app(engine=None, db_path=db_path, ws_port=9876)
        with TestClient(app) as test_client:
            yield test_client


def _login(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200
    return {"csrf_token": response.headers.get("X-CSRF-Token", "")}


def test_admin_runtime_status_returns_diagnostic_snapshot(client: TestClient) -> None:
    tokens = _login(client, "admin", "adminchangeme")

    response = client.get(
        "/api/admin/runtime/status",
        headers={"X-CSRF-Token": tokens["csrf_token"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["providers"]["total"] >= 2
    assert payload["providers"]["active"] >= 2
    assert payload["models"]["visible"] >= 1
    assert payload["fallback"]["provider"] == "ollama"
    assert payload["fallback"]["configured"] is True
    assert payload["tools"]["web_search"]["available"] is True
    assert payload["tools"]["code_sandbox"]["available"] is True
    assert payload["usage"]["deepseek"]["total_tokens"] == 15
    assert payload["observer"]["event_count"] == 1
    assert payload["observer"]["last_event"]["subject"] == "web_search"
    assert payload["notes"]


def test_admin_runtime_status_tolerates_malformed_config_fields(
    client: TestClient,
    runtime_config_path: Path,
) -> None:
    runtime_config_path.write_text(
        json.dumps(
            {
                "providers": ["not", "a", "mapping"],
                "models": "not-a-mapping",
            }
        ),
        encoding="utf-8",
    )
    tokens = _login(client, "admin", "adminchangeme")

    response = client.get(
        "/api/admin/runtime/status",
        headers={"X-CSRF-Token": tokens["csrf_token"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["providers"]["total"] == 0
    assert payload["fallback"]["configured"] is False
    assert payload["notes"]


def test_non_admin_cannot_read_runtime_status(client: TestClient) -> None:
    tokens = _login(client, "alice", "pass123")

    response = client.get(
        "/api/admin/runtime/status",
        headers={"X-CSRF-Token": tokens["csrf_token"]},
    )

    assert response.status_code == 403
