from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.accounts import AccountPrincipal, AccountRole
from app.features.elfies import ElfiesService
from app.interfaces.api.v1.admin.elfies.routes import router as admin_router
from app.interfaces.api.v1.auth import require_user
from app.interfaces.api.v1.elfies.routes import router as member_router
from elfie.profile import create_visual_profile
from infrastructure.persistence.elfie_workspace.brain_state import (
    YamlSelfhoodSeedAdapter,
)
from infrastructure.persistence.elfie_workspace.elfies import (
    SQLiteElfiesProjectionAdapter,
)
from infrastructure.persistence.layout.data_layout import final_root_layout
from infrastructure.persistence.nest_db.store import get_db, init_db
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter


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
                   elfie_id,owner_user_id,adopted_at,status
               ) VALUES
                   ('00000001',1,'2026-08-01T00:00:00Z','offline'),
                   ('00000002',2,'2026-08-02T00:00:00Z','offline')"""
        )
        connection.commit()
    for elfie_id, display_name, species_id, expression in (
        ("00000001", "小狐", "fox", "好奇探索"),
        ("00000002", "小犬", "dog", "安静温顺"),
    ):
        layout = final_root_layout(tmp_path).elfie(elfie_id)
        YamlProfileStoreAdapter(layout.profile.parent).save(
            create_visual_profile(
                elfie_id=elfie_id,
                display_name=display_name,
                species_id=species_id,
                seed=1,
            )
        )
        YamlSelfhoodSeedAdapter(layout.brain).save(
            {
                "state_schema_version": 1,
                "revision": 1,
                "committed_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
                "identity_core": {
                    "elfie_id": elfie_id,
                    "display_name": display_name,
                    "species_id": species_id,
                    "species_name": species_id,
                    "resident_role": "ElfieNest 居民",
                },
                "adaptive_self": {"expression_tendency_ids": [expression]},
            }
        )
    application = FastAPI()
    elfie_projection = SQLiteElfiesProjectionAdapter(db_path)
    application.state.elfies = ElfiesService(elfie_projection, elfie_projection)
    application.dependency_overrides[require_user] = lambda: principal
    application.include_router(member_router)
    application.include_router(admin_router)
    return TestClient(application)


def test_member_resources_return_visible_envelopes_and_owned_profile(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path, principal=_principal())

    listing = client.get("/api/v1/elfies")
    detail = client.get("/api/v1/elfies/00000001/profile")
    owned_listing = client.get("/api/v1/elfies?relationship=owned")

    assert listing.status_code == 200
    assert [item["profile"]["elfie_id"] for item in listing.json()["items"]] == [
        "00000001",
        "00000002",
    ]
    assert [item["relationship"] for item in listing.json()["items"]] == [
        "owned",
        "other",
    ]
    assert listing.json()["items"][0]["relationship"] == "owned"
    assert listing.json()["items"][0]["profile"]["species"]["display_name_zh"] == "灵狐"
    assert owned_listing.status_code == 200
    assert [item["profile"]["elfie_id"] for item in owned_listing.json()["items"]] == [
        "00000001"
    ]
    assert not {
        "food_policy",
        "nest",
        "embodiment",
        "communication",
    }.intersection(listing.json()["items"][0]["profile"])
    assert detail.status_code == 200
    assert detail.json()["private_cognition"]["status"] == "empty"
    assert set(detail.json()) == {
        "relationship",
        "permissions",
        "profile",
        "private_cognition",
    }


def test_member_profile_of_another_member_exposes_public_projection(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path, principal=_principal())

    response = client.get("/api/v1/elfies/00000002/profile")

    assert response.status_code == 200
    assert response.json()["relationship"] == "other"
    assert response.json()["permissions"] == {
        "can_view_profile": True,
        "can_view_cognition": False,
    }
    assert response.json()["private_cognition"] is None


def test_member_profile_exposes_a_private_persisted_headshot(tmp_path: Path) -> None:
    client = _client(tmp_path, principal=_principal())
    portrait = final_root_layout(tmp_path).elfie("00000001").portrait_headshot
    portrait.parent.mkdir(parents=True, exist_ok=True)
    payload = b"\x89PNG\r\n\x1a\nportrait"
    portrait.write_bytes(payload)

    listing = client.get("/api/v1/elfies")
    assert listing.json()["items"][0]["profile"]["portrait_url"] == (
        "/api/v1/elfies/00000001/portrait"
    )
    image = client.get("/api/v1/elfies/00000001/portrait")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert image.content == payload

    hidden = client.get("/api/v1/elfies/00000002/portrait")
    assert hidden.status_code == 404


def test_owner_can_upload_portrait_and_read_it_afterwards(tmp_path: Path) -> None:
    client = _client(tmp_path, principal=_principal())
    payload = b"\x89PNG\r\n\x1a\nupdated"

    response = client.put(
        "/api/v1/elfies/00000001/portrait",
        files={"file": ("portrait.png", payload, "image/png")},
    )

    assert response.status_code == 200
    assert response.json() == {"portrait_url": "/api/v1/elfies/00000001/portrait"}
    image = client.get("/api/v1/elfies/00000001/portrait")
    assert image.content == payload
    assert image.headers["cache-control"] == "no-store"
    assert client.get("/api/v1/elfies/00000001/profile").json()["profile"][
        "portrait_url"
    ] == ("/api/v1/elfies/00000001/portrait")
    assert client.get("/api/v1/elfies").json()["items"][0]["profile"][
        "portrait_url"
    ] == ("/api/v1/elfies/00000001/portrait")


def test_portrait_upload_is_owner_only(tmp_path: Path) -> None:
    client = _client(tmp_path, principal=_principal(user_id=2))
    payload = b"\x89PNG\r\n\x1a\nnot-owner"

    response = client.put(
        "/api/v1/elfies/00000001/portrait",
        files={"file": ("portrait.png", payload, "image/png")},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "elfies_forbidden"
    assert not final_root_layout(tmp_path).elfie("00000001").portrait_headshot.exists()


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
