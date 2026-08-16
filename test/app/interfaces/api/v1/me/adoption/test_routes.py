from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.accounts import AccountPrincipal
from app.features.adoption import AdoptionPolicyRecord, AdoptionService, CandidateReveal
from app.interfaces.api.runtime_capability import RuntimeCapabilityDenied
from app.interfaces.api.v1.auth import require_user
from app.interfaces.api.v1.me.adoption.dependencies import (
    adoption_service,
    resident_admission_service,
)
from app.interfaces.api.v1.me.adoption.routes import router
from app.orchestration.resident_admission import ResidentAdmissionService
from elfie import ElfieFactory
from infrastructure.persistence.adoption import SQLiteAdoptionAdapter
from infrastructure.persistence.elfie_workspace.adoption_profiles import (
    FinalElfieWorkspaceAdapter,
)
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.persistence.nest_db.store import get_db, init_db
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter
from infrastructure.platform import ElfieFactoryAdapter


class Policy:
    def load_policy(self) -> AdoptionPolicyRecord:
        return AdoptionPolicyRecord(3, ("好奇探索",))


class Narrative:
    def is_ready(self) -> bool:
        return True

    def reveal(self, candidate, invitation_message: str) -> CandidateReveal:
        return CandidateReveal("Vulpes", "小狐", "我喜欢在安静的地方慢慢观察世界。")

    def reveal_many(self, candidates, invitation_message: str):
        return {
            candidate.candidate_id: self.reveal(candidate, invitation_message)
            for candidate in candidates
        }


def _client(tmp_path: Path) -> tuple[TestClient, str]:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        connection.execute(
            """INSERT INTO nest_settings(nest_id,bed_count,tick_interval_sec)
               VALUES ('local-nest',4,0.5)"""
        )
        user_id = int(
            connection.execute(
                """INSERT INTO users(account_id,password_hash,role)
                   VALUES ('alice','unused','user')"""
            ).lastrowid
        )
        connection.commit()
    adoption = AdoptionService(
        Policy(), SQLiteAdoptionAdapter(db_path), narrative=Narrative()
    )
    admission = ResidentAdmissionService(
        adoption,
        FinalElfieWorkspaceAdapter(tmp_path),
        ElfieFactoryAdapter(
            ElfieFactory(),
            lambda _elfie_id, _workspace: None,
            lambda workspace: YamlProfileStoreAdapter(Path(workspace) / "profile"),
            lambda workspace: SQLiteMemoryStoreAdapter(
                Path(workspace) / "memory" / "knowledge.sqlite"
            ),
        ),
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
    assert options.json()["nest_capacity"] == {
        "used": 0,
        "max": 4,
        "remaining": 4,
    }
    assert options.json()["availability"] == "available"
    assert options.json()["species"][0]["appearance_controls"] == [
        {"control_id": "stature", "options": ["small", "standard", "tall", "any"]},
        {"control_id": "build", "options": ["slim", "standard", "round", "any"]},
        {"control_id": "face", "options": ["soft", "balanced", "defined", "any"]},
        {"control_id": "signature", "options": ["warm", "marked", "ears", "any"]},
    ]
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
            "batch_number": 1,
        },
    )
    assert candidates.status_code == 200
    candidate_set = candidates.json()
    selected = candidate_set["candidates"][0]
    assert selected["runtime_appearance"]["species_id"] == "fox"
    assert selected["full_body_image_url"] == ""
    assert selected["headshot_image_url"] == ""

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


def test_adoption_is_rejected_until_world_and_models_are_ready(tmp_path: Path) -> None:
    client, _db_path = _client(tmp_path)

    class DenyAdoption:
        def require(self, operation: str) -> None:
            assert operation == "adoption"
            raise RuntimeCapabilityDenied(
                "MODEL_SERVICE_NOT_READY", "领养所需的强模型服务尚未就绪"
            )

    client.app.state.runtime_capability_gate = DenyAdoption()
    response = client.get("/api/v1/me/adoption")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MODEL_SERVICE_NOT_READY"


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
            "batch_number": 1,
            "user_id": 999,
        },
    )

    assert response.status_code == 422


def test_options_report_global_nest_full_before_member_quota(tmp_path: Path) -> None:
    client, db_path = _client(tmp_path)
    with get_db(db_path) as connection:
        owner_id = int(
            connection.execute(
                "SELECT id FROM users WHERE account_id='alice'"
            ).fetchone()[0]
        )
        for index in range(4):
            connection.execute(
                """INSERT INTO elfies(
                       elfie_id,name,owner_user_id,species,gender,birth_date,
                       adopted_at,status,summary
                   ) VALUES (?,?,?,'fox','female','2000-01-01',
                             CURRENT_TIMESTAMP,'offline','steady')""",
                (f"{index + 1:08d}", f"Elfie {index + 1}", owner_id),
            )
        connection.commit()

    options = client.get("/api/v1/me/adoption")

    assert options.status_code == 200
    assert options.json()["availability"] == "nest_full"
    assert options.json()["nest_capacity"]["remaining"] == 0
