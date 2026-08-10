"""Full-app TestClient acceptance for the Owner member lifecycle."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import build_application_container, create_app
from infrastructure.persistence.store import init_db

from ._helpers import create_test_owner


def _csrf(response) -> dict[str, str]:
    return {"X-CSRF-Token": response.headers["X-CSRF-Token"]}


def test_complete_member_administration_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = str(tmp_path / "nest.db")
    home = tmp_path / "home"
    monkeypatch.setenv("ELFIE_HOME", str(home))
    init_db(db_path)
    create_test_owner(db_path, account_id="owner01", password="owner-password")
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        with TestClient(application) as client:
            owner_login = client.post(
                "/api/v1/auth/login",
                data={"account_id": "owner01", "password": "owner-password"},
            )
            assert owner_login.status_code == 200, owner_login.text
            owner_headers = _csrf(owner_login)
            listed = client.get("/api/v1/admin/users", headers=owner_headers)
            assert listed.status_code == 200
            assert listed.json()["items"][0]["role"] == "owner"

            created = client.post(
                "/api/v1/admin/users",
                json={
                    "account_id": "member01",
                    "display_name": "Member",
                    "password": "old-member-password",
                    "role": "user",
                },
                headers=owner_headers,
            )
            assert created.status_code == 201, created.text
            member_id = created.json()["user_id"]
            updated = client.patch(
                f"/api/v1/admin/users/{member_id}",
                json={"elfie_quota_override": 6},
                headers=owner_headers,
            )
            assert updated.status_code == 200
            assert updated.json()["effective_elfie_limit"] == 6

            accounts = build_application_container(db_path).accounts
            old_token_one = accounts.create_session(member_id)
            old_token_two = accounts.create_session(member_id)
            reset = client.post(
                f"/api/v1/admin/users/{member_id}/reset-password",
                headers=owner_headers,
            )
            assert reset.status_code == 200, reset.text
            temporary_password = reset.json()["temporary_password"]

            for old_token in (old_token_one, old_token_two):
                client.cookies.clear()
                client.cookies.set("session_token", old_token)
                rejected = client.get("/api/v1/me")
                assert rejected.status_code == 401

            temporary_login = client.post(
                "/api/v1/auth/login",
                data={
                    "account_id": "member01",
                    "password": temporary_password,
                },
            )
            assert temporary_login.status_code == 200, temporary_login.text
            assert temporary_login.json()["user"]["user_id"] == member_id
            member_headers = _csrf(temporary_login)
            logout = client.post("/api/v1/auth/logout", headers=member_headers)
            assert logout.status_code == 200

            owner_login = client.post(
                "/api/v1/auth/login",
                data={"account_id": "owner01", "password": "owner-password"},
            )
            deleted = client.delete(
                f"/api/v1/admin/users/{member_id}", headers=_csrf(owner_login)
            )
            assert deleted.status_code == 204
