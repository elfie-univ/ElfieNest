import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from elfienest.api.app import create_app
from elfienest.persistence.store import init_db
from runtime.usage.observer import (
    FallbackObservation,
    RuntimeEventStatus,
    RuntimeObserver,
    ToolCallObservation,
)
from runtime.usage.token_tracker import TokenTracker

from ._helpers import create_test_owner, create_test_user


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
                "runtime_policy": {
                    "task_routes": {"reasoning": "premium"},
                    "model_groups": {
                        "premium": {
                            "display_name": "精粮",
                            "model_keys": ["remote_deep", "local_fast"],
                        }
                    },
                    "tool_permissions": {
                        "RUN_SKILL": {
                            "mode": "allow",
                            "reason": "技能运行允许",
                        }
                    },
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
    create_test_owner(db_path)
    create_test_user(db_path, "alice", "pass123")

    with (
        patch("elfienest.api.app.AuthenticatedWSManager.start"),
        patch("elfienest.api.app.AuthenticatedWSManager.stop"),
        patch("elfienest.api.runtime_routes.get_config_path", return_value=runtime_config_path),
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


def test_owner_runtime_status_returns_diagnostic_snapshot(client: TestClient) -> None:
    tokens = _login(client, "owner", "ownerchangeme")

    response = client.get(
        "/api/owner/runtime/status",
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
    assert payload["observer"]["event_count"] == 2
    assert payload["observer"]["last_event"]["subject"] == "local_fast"
    assert payload["notes"]


def test_owner_runtime_status_tolerates_malformed_config_fields(
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
    tokens = _login(client, "owner", "ownerchangeme")

    response = client.get(
        "/api/owner/runtime/status",
        headers={"X-CSRF-Token": tokens["csrf_token"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["providers"]["total"] == 0
    assert payload["fallback"]["configured"] is False
    assert payload["notes"]


def test_non_owner_cannot_read_runtime_status(client: TestClient) -> None:
    tokens = _login(client, "alice", "pass123")

    response = client.get(
        "/api/owner/runtime/status",
        headers={"X-CSRF-Token": tokens["csrf_token"]},
    )

    assert response.status_code == 403


def test_owner_runtime_policy_returns_configured_strategy(client: TestClient) -> None:
    tokens = _login(client, "owner", "ownerchangeme")

    response = client.get(
        "/api/owner/runtime/policy",
        headers={"X-CSRF-Token": tokens["csrf_token"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_routes"]["reasoning"] == "premium"
    assert "model_groups_deprecated" not in payload
    assert "focus" in payload["food_keys"]
    assert payload["tool_permissions"]["RUN_SKILL"]["mode"] == "allow"
    assert payload["tool_permissions"]["DELETE_SKILL"]["mode"] == "owner"


def test_owner_runtime_policy_put_persists_strategy(
    client: TestClient,
    runtime_config_path: Path,
) -> None:
    tokens = _login(client, "owner", "ownerchangeme")

    response = client.put(
        "/api/owner/runtime/policy",
        json={
            "task_routes": {"reasoning": "standard"},
            "tool_permissions": {
                "RUN_SKILL": {
                    "mode": "ask",
                    "reason": "需要人工确认",
                }
            },
        },
        headers={"X-CSRF-Token": tokens["csrf_token"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_routes"]["reasoning"] == "standard"
    assert payload["tool_permissions"]["RUN_SKILL"]["mode"] == "ask"

    saved = json.loads(runtime_config_path.read_text(encoding="utf-8"))
    assert saved["runtime_policy"]["task_routes"]["reasoning"] == "standard"


def test_owner_runtime_policy_rejects_direct_model_groups(client: TestClient) -> None:
    tokens = _login(client, "owner", "ownerchangeme")

    response = client.put(
        "/api/owner/runtime/policy",
        json={
            "model_groups": {
                "premium": {"model_keys": ["remote_deep"]},
            }
        },
        headers={"X-CSRF-Token": tokens["csrf_token"]},
    )

    assert response.status_code == 410
    assert "模型由粮食配方管理" in response.text


def test_owner_runtime_policy_rejects_invalid_permission_mode(
    client: TestClient,
) -> None:
    tokens = _login(client, "owner", "ownerchangeme")

    response = client.put(
        "/api/owner/runtime/policy",
        json={"tool_permissions": {"RUN_SKILL": {"mode": "unknown"}}},
        headers={"X-CSRF-Token": tokens["csrf_token"]},
    )

    assert response.status_code == 422


def test_owner_runtime_policy_rejects_invalid_task_route(
    client: TestClient,
) -> None:
    tokens = _login(client, "owner", "ownerchangeme")

    response = client.put(
        "/api/owner/runtime/policy",
        json={"task_routes": {"unknown": "premium"}},
        headers={"X-CSRF-Token": tokens["csrf_token"]},
    )

    assert response.status_code == 422


def test_owner_runtime_audit_returns_recent_events(client: TestClient) -> None:
    tokens = _login(client, "owner", "ownerchangeme")

    response = client.get(
        "/api/owner/runtime/audit",
        headers={"X-CSRF-Token": tokens["csrf_token"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["event_count"] == 2
    assert payload["events"][0]["event_type"] == "tool_call"
    assert payload["events"][1]["event_type"] == "fallback"


def test_non_owner_cannot_read_runtime_policy_or_audit(client: TestClient) -> None:
    tokens = _login(client, "alice", "pass123")

    policy_response = client.get(
        "/api/owner/runtime/policy",
        headers={"X-CSRF-Token": tokens["csrf_token"]},
    )
    audit_response = client.get(
        "/api/owner/runtime/audit",
        headers={"X-CSRF-Token": tokens["csrf_token"]},
    )

    assert policy_response.status_code == 403
    assert audit_response.status_code == 403
