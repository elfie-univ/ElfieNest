from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.accounts import AccountPrincipal, AccountRole
from app.infrastructure.persistence.store import get_db, init_db
from app.interfaces.api.v1.admin.runtime.embodiment_sessions.routes import router
from app.interfaces.api.v1.auth import require_user
from app.orchestration.embodiment import EmbodimentSessionService
from infrastructure.persistence.embodiment import SQLiteEmbodimentLeaseAdapter


def _principal(role: AccountRole) -> AccountPrincipal:
    return AccountPrincipal(
        user_id=1,
        account_id="alice",
        role=role,
        default_landing_page="/chat",
    )


def _client(tmp_path: Path, role: AccountRole) -> TestClient:
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT INTO users(id,account_id,role,password_hash) "
            "VALUES (1,'alice','owner','hash')"
        )
        connection.execute(
            """INSERT INTO elfies(
                   elfie_id,name,owner_user_id,species,adopted_at,status
               ) VALUES ('00000001','小狐',1,'fox','2026-08-01','offline')"""
        )
        connection.commit()
    application = FastAPI()
    application.state.db_path = db_path
    application.state.embodiment = EmbodimentSessionService(
        SQLiteEmbodimentLeaseAdapter(db_path)
    )
    application.dependency_overrides[require_user] = lambda: _principal(role)
    application.include_router(router)
    return TestClient(application)


def test_manager_lists_existing_sessions_without_materializing_missing_rows(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path, "admin")

    response = client.get("/api/v1/admin/runtime/embodiment-sessions")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {"elfie_id": "00000001", "state": "at_nest", "body_id": None}
        ]
    }
    with get_db(client.app.state.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM embodiment_sessions").fetchone()[0] == 0


def test_member_cannot_list_embodiment_sessions(tmp_path: Path) -> None:
    response = _client(tmp_path, "user").get(
        "/api/v1/admin/runtime/embodiment-sessions"
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "embodiment_sessions_forbidden"
