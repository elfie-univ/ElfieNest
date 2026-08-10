from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.accounts import AccountPrincipal, AccountRole
from app.features.elfies import ElfiesService
from infrastructure.persistence.store import get_db, init_db
from app.interfaces.api.v1.admin.elfies.routes import router as admin_router
from app.interfaces.api.v1.auth import require_user
from app.interfaces.api.v1.elfies.routes import router as member_router
from infrastructure.persistence.elfies import SQLiteElfiesProjectionAdapter


def _principal(
    user_id: int = 1,
    role: AccountRole = "user",
) -> AccountPrincipal:
    return AccountPrincipal(
        user_id=user_id,
        account_id="alice",
        role=role,
        default_landing_page="/chat",
    )


def _client(
    tmp_path: Path,
    *,
    principal: AccountPrincipal,
) -> TestClient:
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT INTO users(id,account_id,role,password_hash) "
            "VALUES (1,'alice','owner','hash'),(2,'bob','user','hash')"
        )
        connection.execute(
            """INSERT INTO elfies(
                   elfie_id,name,owner_user_id,species,adopted_at,status,summary
               ) VALUES
                   ('00000001','小狐',1,'fox','2026-08-01T00:00:00Z','offline','好奇探索'),
                   ('00000002','小犬',2,'dog','2026-08-02T00:00:00Z','offline','安静温顺')"""
        )
        connection.commit()
    application = FastAPI()
    application.state.elfies = ElfiesService(SQLiteElfiesProjectionAdapter(db_path))
    application.dependency_overrides[require_user] = lambda: principal
    application.include_router(member_router)
    application.include_router(admin_router)
    return TestClient(application)


def test_member_resources_return_owned_envelope_and_profile(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path, principal=_principal())

    listing = client.get("/api/v1/elfies")
    detail = client.get("/api/v1/elfies/00000001/profile")

    assert listing.status_code == 200
    assert [item["profile"]["elfie_id"] for item in listing.json()["items"]] == [
        "00000001"
    ]
    assert listing.json()["items"][0]["relationship"] == "owned"
    assert detail.status_code == 200
    assert detail.json()["private_cognition"]["status"] == "empty"
    assert set(detail.json()) == {
        "relationship",
        "permissions",
        "profile",
        "private_cognition",
    }


def test_member_profile_hides_another_members_elfie(tmp_path: Path) -> None:
    client = _client(tmp_path, principal=_principal())

    response = client.get("/api/v1/elfies/00000002/profile")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "elfie_not_found"


def test_admin_directory_is_separate_and_feature_authorized(tmp_path: Path) -> None:
    member = _client(tmp_path / "member", principal=_principal())
    manager = _client(tmp_path / "manager", principal=_principal(role="admin"))

    forbidden = member.get("/api/v1/admin/elfies")
    listing = manager.get("/api/v1/admin/elfies?owner_user_id=2")

    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "elfies_forbidden"
    assert listing.status_code == 200
    assert [item["profile"]["elfie_id"] for item in listing.json()["items"]] == [
        "00000002"
    ]
    assert listing.json()["items"][0]["owner"]["account_id"] == "bob"
    assert listing.json()["items"][0]["permissions"]["can_view_cognition"] is False
