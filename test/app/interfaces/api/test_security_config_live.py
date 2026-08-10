"""Live security settings through the injected Accounts facade."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.infrastructure.persistence.store import get_db, init_db
from infrastructure.persistence import hash_session_token
from test.app.interfaces.api._helpers import create_test_owner


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    db_path = str(tmp_path / "nest.db")
    runtime_config_path = tmp_path / "configs" / "runtime.yaml"
    init_db(db_path)
    create_test_owner(db_path)
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
        patch(
            "app.interfaces.api.system_routes.get_config_path",
            return_value=runtime_config_path,
        ),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        with TestClient(application, base_url="http://127.0.0.1:8000") as test_client:
            yield test_client


def _login(client: TestClient, password: str = "ownerchangeme"):
    return client.post(
        "/api/v1/auth/login",
        data={"account_id": "owner", "password": password},
    )


def _owner_headers(client: TestClient) -> dict[str, str]:
    response = _login(client)
    assert response.status_code == 200
    return {"X-CSRF-Token": response.headers["X-CSRF-Token"]}


def test_session_ttl_setting_applies_to_new_login(client: TestClient) -> None:
    headers = _owner_headers(client)
    response = client.put(
        "/api/owner/system/security",
        json={"session_ttl_days": 1},
        headers=headers,
    )
    assert response.status_code == 200

    login = _login(client)
    assert login.status_code == 200
    session_token = login.cookies["session_token"]
    with get_db(client.app.state.db_path) as connection:
        row = connection.execute(
            "SELECT expires_at FROM sessions WHERE token_hash=?",
            (hash_session_token(session_token),),
        ).fetchone()
    expires_at = datetime.fromisoformat(row["expires_at"]).timestamp()
    assert abs((expires_at - time.time()) - 86_400) < 5


def test_login_rate_limit_setting_applies_without_rebuilding_app(
    client: TestClient,
) -> None:
    headers = _owner_headers(client)
    response = client.put(
        "/api/owner/system/security",
        json={"rate_limit": {"max_attempts": 2, "window_seconds": 300}},
        headers=headers,
    )
    assert response.status_code == 200

    assert _login(client, "wrong-1").status_code == 401
    assert _login(client, "wrong-2").status_code == 401
    limited = _login(client, "wrong-3")
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "login_rate_limited"


@pytest.mark.parametrize(
    "payload",
    [
        {"session_ttl_days": 0},
        {"rate_limit": {"max_attempts": 0, "window_seconds": 300}},
        {"rate_limit": {"max_attempts": 5, "window_seconds": 0}},
        {"unknown_field": "value"},
    ],
)
def test_invalid_security_settings_remain_rejected(
    client: TestClient, payload: dict
) -> None:
    response = client.put(
        "/api/owner/system/security",
        json=payload,
        headers=_owner_headers(client),
    )
    assert response.status_code == 422
