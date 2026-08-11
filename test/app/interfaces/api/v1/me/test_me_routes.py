from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.accounts import (
    AccountPrincipal,
    AccountsService,
    hash_password,
)
from app.interfaces.api.v1.auth import require_user
from app.interfaces.api.v1.me import router
from infrastructure.persistence.accounts import SQLiteAccountsAdapter
from infrastructure.persistence.store import get_db, init_db


class QuotaPolicy:
    def default_elfie_limit(self) -> int:
        return 3


def _client(tmp_path: Path) -> tuple[TestClient, int]:
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        user_id = connection.execute(
            "INSERT INTO users (account_id,password_hash,role,display_name) "
            "VALUES (?,?, 'owner', ?)",
            ("owner", hash_password("old-password"), "Owner"),
        ).lastrowid
        connection.commit()
    assert user_id is not None
    adapter = SQLiteAccountsAdapter(db_path)
    service = AccountsService(
        management=adapter,
        avatars=adapter,
        quota_policy=QuotaPolicy(),
    )
    app = FastAPI()
    app.state.accounts = service
    app.dependency_overrides[require_user] = lambda: AccountPrincipal(
        int(user_id), "owner", "owner", "manage"
    )
    app.include_router(router)
    return TestClient(app), int(user_id)


def test_current_profile_theme_and_landing_use_strict_v1_resources(
    tmp_path: Path,
) -> None:
    client, user_id = _client(tmp_path)

    current = client.get("/api/v1/me")
    profile = client.patch(
        "/api/v1/me/profile",
        json={"display_name": "Owner New", "gender": "female"},
    )
    theme = client.put("/api/v1/me/theme", json={"theme_key": "moss-green"})
    landing = client.put(
        "/api/v1/me/default-landing-page",
        json={"default_landing_page": "chat"},
    )

    assert current.status_code == 200
    assert current.json()["user_id"] == user_id
    assert current.json()["avatar_url"] is None
    assert profile.status_code == 200
    assert profile.json()["display_name"] == "Owner New"
    assert profile.json()["gender"] == "female"
    assert theme.json() == {"theme_key": "moss-green"}
    assert landing.json() == {"default_landing_page": "chat"}


def test_heartbeat_updates_the_authenticated_current_account(tmp_path: Path) -> None:
    client, user_id = _client(tmp_path)

    response = client.post("/api/v1/me/heartbeat")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    response_timestamp = datetime.fromisoformat(
        response.json()["last_seen_at"].replace("Z", "+00:00")
    )
    assert response_timestamp.utcoffset() is not None
    with get_db(str(tmp_path / "nest.db")) as connection:
        row = connection.execute(
            "SELECT presence,last_seen_at FROM users WHERE id=?", (user_id,)
        ).fetchone()
    assert row["presence"] == "online"
    assert datetime.fromisoformat(row["last_seen_at"]) == response_timestamp


def test_password_and_avatar_errors_use_stable_error_envelopes(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    password = client.post(
        "/api/v1/me/password",
        json={"old_password": "wrong", "new_password": "new-password"},
    )
    avatar = client.post(
        "/api/v1/me/avatar",
        files={"file": ("avatar.png", b"not-an-image", "image/png")},
    )

    assert password.status_code == 400
    assert password.json()["error"]["code"] == "current_password_incorrect"
    assert avatar.status_code == 415
    assert avatar.json()["error"]["code"] == "invalid_avatar_content"


def test_avatar_round_trip_returns_binary_without_a_local_path(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    content = b"\x89PNG\r\n\x1a\ncontent"

    uploaded = client.post(
        "/api/v1/me/avatar",
        files={"file": ("avatar.png", content, "image/png")},
    )
    loaded = client.get("/api/v1/me/avatar")

    assert uploaded.status_code == 201
    assert uploaded.json() == {"avatar_url": "/api/v1/me/avatar"}
    assert loaded.status_code == 200
    assert loaded.content == content
    assert loaded.headers["cache-control"] == "no-store"
