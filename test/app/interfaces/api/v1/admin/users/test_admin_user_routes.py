from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.accounts import AccountPrincipal, AccountsService, hash_password
from app.infrastructure.persistence.store import get_db, init_db
from app.interfaces.api.v1.admin.users import router
from app.interfaces.api.v1.auth import require_user
from infrastructure.persistence import SQLiteAccountsAdapter


class QuotaPolicy:
    def default_elfie_limit(self) -> int:
        return 4


def _client(tmp_path: Path, role: str = "owner") -> TestClient:
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        owner_id = connection.execute(
            "INSERT INTO users (account_id,password_hash,role) VALUES (?,?, 'owner')",
            ("owner", hash_password("owner-password")),
        ).lastrowid
        connection.commit()
    assert owner_id is not None
    adapter = SQLiteAccountsAdapter(db_path)
    app = FastAPI()
    app.state.accounts = AccountsService(
        management=adapter,
        avatars=adapter,
        quota_policy=QuotaPolicy(),
    )
    app.dependency_overrides[require_user] = lambda: AccountPrincipal(
        int(owner_id), "owner", role, "manage"
    )
    app.include_router(router)
    return TestClient(app)


def test_admin_user_lifecycle_preserves_existing_capabilities(tmp_path: Path) -> None:
    client = _client(tmp_path)

    created = client.post(
        "/api/v1/admin/users",
        json={
            "account_id": "member01",
            "display_name": "Member",
            "password": "member-password",
            "role": "user",
        },
    )
    user_id = created.json()["user_id"]
    listed = client.get("/api/v1/admin/users")
    quota = client.patch(
        f"/api/v1/admin/users/{user_id}",
        json={"elfie_quota_override": 6},
    )
    reset = client.post(f"/api/v1/admin/users/{user_id}/reset-password")
    deleted = client.delete(f"/api/v1/admin/users/{user_id}")

    assert created.status_code == 201
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 2
    assert quota.json()["effective_elfie_limit"] == 6
    assert len(reset.json()["temporary_password"]) == 12
    assert deleted.status_code == 204
    assert deleted.content == b""


def test_admin_cannot_create_or_mutate_a_peer_admin(tmp_path: Path) -> None:
    client = _client(tmp_path, role="admin")

    created = client.post(
        "/api/v1/admin/users",
        json={
            "account_id": "admin02",
            "display_name": None,
            "password": "admin-password",
            "role": "admin",
        },
    )

    assert created.status_code == 403
    assert created.json()["error"]["code"] == "account_forbidden"


def test_admin_users_rejects_loose_or_empty_mutations(tmp_path: Path) -> None:
    client = _client(tmp_path)

    loose_create = client.post(
        "/api/v1/admin/users",
        json={
            "account_id": "member01",
            "password": "member-password",
            "role": "user",
            "username": "legacy",
        },
    )
    empty_patch = client.patch("/api/v1/admin/users/1", json={})

    assert loose_create.status_code == 422
    assert empty_patch.status_code == 422
    assert empty_patch.json()["error"]["code"] == "invalid_account_request"
