"""Focused final-contract tests for Owner member administration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_runtime.storage.data_layout import final_root_layout
from app.features.accounts.auth import require_owner
from app.infrastructure.persistence.session_repository import SessionRepository
from app.infrastructure.persistence.store import get_db, init_db, verify_password
from app.interfaces.api.owner_user_routes import router

from ._helpers import create_test_owner

_VIEW_FIELDS = {
    "user_id",
    "account_id",
    "display_name",
    "role",
    "gender",
    "birth_date",
    "presence",
    "last_seen_at",
    "language",
    "created_at",
    "elfie_count",
    "elfie_quota_override",
    "effective_elfie_limit",
    "avatar_url",
}


@pytest.fixture
def administration_db_path(tmp_path: Path) -> str:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_test_owner(db_path, account_id="owner01")
    return db_path


@pytest.fixture
def administration_client(
    administration_db_path: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path / "home"))
    application = FastAPI()
    application.state.db_path = administration_db_path
    application.include_router(router)
    application.dependency_overrides[require_owner] = lambda: {
        "user_id": 1,
        "account_id": "owner01",
        "role": "owner",
        "default_landing_page": "manage",
    }
    with TestClient(application, raise_server_exceptions=False) as client:
        yield client


def _create_member(client: TestClient, account_id: str = "member01") -> dict:
    response = client.post(
        "/api/owner/users",
        json={
            "account_id": account_id,
            "display_name": " Member ",
            "password": "member-password",
            "role": "user",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_owner_user_view_and_create_payload_use_only_final_fields(
    administration_client: TestClient,
) -> None:
    created = _create_member(administration_client)

    assert set(created) == _VIEW_FIELDS
    assert isinstance(created["user_id"], int)
    assert created["account_id"] == "member01"
    assert created["display_name"] == "Member"
    listed = administration_client.get("/api/owner/users")
    assert listed.status_code == 200
    assert [row["role"] for row in listed.json()] == ["owner", "user"]
    assert all(set(row) == _VIEW_FIELDS for row in listed.json())

    legacy = administration_client.post(
        "/api/owner/users",
        json={"username": "legacy", "password": "password", "role": "user"},
    )
    assert legacy.status_code == 422


def test_user_list_reads_adoption_limit_from_selected_database_root(
    administration_client: TestClient, administration_db_path: str
) -> None:
    selected_root = Path(administration_db_path).parent
    config_path = final_root_layout(selected_root).runtime_config
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "system:\n  adoption:\n    max_elfies_per_user: 9\n",
        encoding="utf-8",
    )

    response = administration_client.get("/api/owner/users")

    assert response.status_code == 200
    assert response.json()[0]["effective_elfie_limit"] == 9


@pytest.mark.parametrize("password", ["short", "      ", " 1234 "])
def test_member_creation_rejects_weak_initial_passwords(
    administration_client: TestClient, password: str
) -> None:
    response = administration_client.post(
        "/api/owner/users",
        json={
            "account_id": "weak-member",
            "password": password,
            "role": "user",
        },
    )
    assert response.status_code == 422


def test_member_quota_and_delete_use_numeric_user_id(
    administration_client: TestClient,
) -> None:
    member = _create_member(administration_client)
    user_id = member["user_id"]

    updated = administration_client.put(
        f"/api/owner/users/{user_id}", json={"elfie_quota_override": 6}
    )
    assert updated.status_code == 200
    assert updated.json()["user_id"] == user_id
    assert updated.json()["elfie_quota_override"] == 6
    deleted = administration_client.delete(f"/api/owner/users/{user_id}")
    assert deleted.status_code == 200


@pytest.mark.parametrize("operation", ["quota", "reset", "delete"])
def test_owner_mutations_are_forbidden(
    administration_client: TestClient,
    administration_db_path: str,
    operation: str,
) -> None:
    with get_db(administration_db_path) as connection:
        before = tuple(connection.execute("SELECT * FROM users WHERE id=1").fetchone())
    if operation == "quota":
        response = administration_client.put(
            "/api/owner/users/1", json={"elfie_quota_override": 5}
        )
    elif operation == "reset":
        response = administration_client.post("/api/owner/users/1/reset-password")
    else:
        response = administration_client.delete("/api/owner/users/1")
    with get_db(administration_db_path) as connection:
        after = tuple(connection.execute("SELECT * FROM users WHERE id=1").fetchone())
    assert response.status_code == 403
    assert after == before


def test_member_with_elfie_cannot_be_deleted(
    administration_client: TestClient,
    administration_db_path: str,
) -> None:
    member = _create_member(administration_client)
    with get_db(administration_db_path) as connection:
        connection.execute(
            """INSERT INTO elfies
               (elfie_id,name,owner_user_id,species,adopted_at,status)
               VALUES ('00000001','Elfie',?,'fox','2026-08-01T00:00:00Z','offline')""",
            (member["user_id"],),
        )
        connection.commit()

    response = administration_client.delete(f"/api/owner/users/{member['user_id']}")
    assert response.status_code == 409


def test_reset_password_is_one_time_plaintext_and_revokes_all_sessions(
    administration_client: TestClient,
    administration_db_path: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    member = _create_member(administration_client)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    with get_db(administration_db_path) as connection:
        SessionRepository(connection).issue(member["user_id"], expires_at)
        SessionRepository(connection).issue(member["user_id"], expires_at)
        connection.commit()

    caplog.set_level(logging.INFO)
    response = administration_client.post(
        f"/api/owner/users/{member['user_id']}/reset-password"
    )
    assert response.status_code == 200, response.text
    temporary_password = response.json()["temporary_password"]
    assert len(temporary_password) == 12
    assert temporary_password.isascii() and temporary_password.isalnum()
    assert temporary_password not in caplog.text
    with get_db(administration_db_path) as connection:
        row = connection.execute(
            "SELECT password_hash FROM users WHERE id=?", (member["user_id"],)
        ).fetchone()
        active = connection.execute(
            "SELECT COUNT(*) FROM sessions WHERE user_id=? AND revoked_at IS NULL",
            (member["user_id"],),
        ).fetchone()[0]
    assert verify_password(temporary_password, row["password_hash"])
    assert active == 0


def test_reset_failure_rolls_back_password_and_session_revocation(
    administration_client: TestClient,
    administration_db_path: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    member = _create_member(administration_client)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    with get_db(administration_db_path) as connection:
        SessionRepository(connection).issue(member["user_id"], expires_at)
        before_hash = connection.execute(
            "SELECT password_hash FROM users WHERE id=?", (member["user_id"],)
        ).fetchone()[0]
        connection.execute(
            """CREATE TRIGGER fail_reset BEFORE UPDATE OF revoked_at ON sessions
               BEGIN SELECT RAISE(ABORT, 'forced reset failure'); END"""
        )
        connection.commit()

    caplog.set_level(logging.INFO)
    with patch(
        "app.features.administration.member_service.secrets.choice",
        return_value="Z",
    ):
        response = administration_client.post(
            f"/api/owner/users/{member['user_id']}/reset-password"
        )
    with get_db(administration_db_path) as connection:
        after_hash = connection.execute(
            "SELECT password_hash FROM users WHERE id=?", (member["user_id"],)
        ).fetchone()[0]
        revoked_at = connection.execute(
            "SELECT revoked_at FROM sessions WHERE user_id=?", (member["user_id"],)
        ).fetchone()[0]
    assert response.status_code == 500
    assert response.text == "Internal Server Error"
    assert after_hash == before_hash
    assert revoked_at is None
    assert "ZZZZZZZZZZZZ" not in caplog.text
