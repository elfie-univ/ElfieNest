from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.accounts import AccountPrincipal
from app.features.adoption import AdoptionPolicyRecord, AdoptionService
from app.infrastructure.persistence.store import get_db, init_db
from app.interfaces.api.v1.auth import require_user
from app.interfaces.api.v1.me.adoption.dependencies import (
    adoption_service,
    resident_admission_service,
)
from app.interfaces.api.v1.me.adoption.routes import router
from app.orchestration.resident_admission import ResidentAdmissionService
from elfie import ElfieFactory
from infrastructure.persistence import FinalElfieWorkspaceAdapter, SQLiteAdoptionAdapter
from infrastructure.platform import ElfieFactoryAdapter


class Policy:
    def load_policy(self) -> AdoptionPolicyRecord:
        return AdoptionPolicyRecord(3, ("dog", "fox"), ("好奇探索",))


def _client(tmp_path: Path) -> tuple[TestClient, str]:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        user_id = int(
            connection.execute(
                """INSERT INTO users(account_id,password_hash,role)
                   VALUES ('alice','unused','user')"""
            ).lastrowid
        )
        connection.commit()
    adoption = AdoptionService(Policy(), SQLiteAdoptionAdapter(db_path))
    admission = ResidentAdmissionService(
        adoption,
        FinalElfieWorkspaceAdapter(tmp_path),
        ElfieFactoryAdapter(ElfieFactory(), None),
        None,
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_user] = lambda: AccountPrincipal(
        user_id,
        "alice",
        "user",
        "chat",
    )
    app.dependency_overrides[adoption_service] = lambda: adoption
    app.dependency_overrides[resident_admission_service] = lambda: admission
    return TestClient(app), db_path


def test_versioned_adoption_resource_preserves_candidate_reply_and_commit(
    tmp_path: Path,
) -> None:
    client, db_path = _client(tmp_path)
    options = client.get("/api/v1/me/adoption")
    assert options.status_code == 200
    assert options.json()["quota"] == {
        "used": 0,
        "max": 3,
        "remaining": 3,
        "can_adopt": True,
    }
    candidates = client.post(
        "/api/v1/me/adoption/candidate-sets",
        json={
            "species_id": "fox",
            "life_stage": "young_adult",
            "gender": "any",
            "appearance": {
                "stature": "tall",
                "build": "round",
                "face": "soft",
                "signature": "warm",
                "priority": "face",
            },
            "answers": ["quiet", "research", "plan", "discuss", "steady"],
        },
    )
    assert candidates.status_code == 200
    candidate_set = candidates.json()
    selected = candidate_set["candidates"][0]

    before_reply = client.post(
        "/api/v1/me/adoption",
        json={
            "candidate_set_id": candidate_set["candidate_set_id"],
            "candidate_id": selected["candidate_id"],
            "name": "星砂",
        },
    )
    assert before_reply.status_code == 409
    assert before_reply.json()["error"]["code"] == "adoption_candidate_not_accepted"

    replies = client.post(
        f"/api/v1/me/adoption/candidate-sets/{candidate_set['candidate_set_id']}/replies",
        json={"candidate_ids": [selected["candidate_id"]]},
    )
    assert replies.status_code == 200
    assert replies.json()["replies"][0]["status"] == "accepted"

    committed = client.post(
        "/api/v1/me/adoption",
        json={
            "candidate_set_id": candidate_set["candidate_set_id"],
            "candidate_id": selected["candidate_id"],
            "name": "星砂",
        },
    )
    assert committed.status_code == 201
    with get_db(db_path) as connection:
        stored = connection.execute(
            "SELECT name,gender,birth_date FROM elfies WHERE elfie_id=?",
            (committed.json()["elfie_id"],),
        ).fetchone()
    assert tuple(stored) == ("星砂", selected["gender"], stored["birth_date"])


def test_adoption_dtos_reject_extra_fields(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    response = client.post(
        "/api/v1/me/adoption/candidate-sets",
        json={
            "species_id": "fox",
            "life_stage": "any",
            "gender": "any",
            "appearance": {
                "stature": "any",
                "build": "any",
                "face": "any",
                "signature": "any",
                "priority": "face",
            },
            "answers": ["any", "any", "any", "any", "any"],
            "user_id": 999,
        },
    )

    assert response.status_code == 422
