from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.accounts import AccountPrincipal
from app.features.adoption import AdoptionPolicyRecord, AdoptionService
from app.interfaces.api.runtime_capability import RuntimeCapabilityDenied
from app.interfaces.api.v1.auth import require_user
from app.interfaces.api.v1.me.adoption.dependencies import (
    adoption_service,
    resident_admission_service,
)
from app.interfaces.api.v1.me.adoption.routes import router
from app.orchestration.resident_admission import ResidentAdmissionService
from elfie import ElfieFactory
from elfie.genesis import GenesisCompiler
from infrastructure.persistence.adoption import SQLiteAdoptionAdapter
from infrastructure.persistence.configuration.species import (
    load_and_configure_species_catalog,
)
from infrastructure.persistence.configuration.world import load_genesis_source_package
from infrastructure.persistence.elfie_workspace.adoption_profiles import (
    FinalElfieWorkspaceAdapter,
)
from infrastructure.persistence.layout.data_layout import final_root_layout
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.persistence.nest_db.store import get_db, init_db
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter
from infrastructure.platform import ElfieFactoryAdapter


class Policy:
    def load_policy(self) -> AdoptionPolicyRecord:
        return AdoptionPolicyRecord(3, ("好奇探索",))


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
    catalog = load_and_configure_species_catalog()
    adoption = AdoptionService(
        Policy(), SQLiteAdoptionAdapter(db_path), catalog=catalog
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
        GenesisCompiler(load_genesis_source_package(), catalog=catalog),
        admission_store=SQLiteAdoptionAdapter(db_path),
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
    committed_id = committed.json()["elfie_id"]
    profile = YamlProfileStoreAdapter(
        final_root_layout(tmp_path).elfie(committed_id).profile.parent
    ).load()
    assert profile.identity.display_name == "星砂"
    assert profile.identity.gender == selected["gender"]
    assert committed.json()["persistence_status"] == "committed"

    workspace = final_root_layout(tmp_path).elfie(committed_id)
    with SQLiteMemoryStoreAdapter(
        workspace.knowledge_database, elfie_id=committed_id
    ) as memory:
        person = memory.get_graph_node(f"genesis:person:{committed_id}:kin-01")
        assert person is not None
        assert person.properties["person_species_id"] == "fox"
        assert person.properties["vocation_id"] == "plant_cultivator"
        assert person.properties["episode_ids"]
        assert memory.count_episodes() == 5
        assert memory.count_graph_nodes("knowledge") == 40
    assert not workspace.genesis_compile_envelope.exists()
    assert not workspace.genesis_stage_marker.exists()


def test_adoption_is_rejected_when_the_runtime_capability_is_denied(
    tmp_path: Path,
) -> None:
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
                       elfie_id,owner_user_id,adopted_at,status
                   ) VALUES (?,?,CURRENT_TIMESTAMP,'offline')""",
                (f"{index + 1:08d}", owner_id),
            )
        connection.commit()

    options = client.get("/api/v1/me/adoption")

    assert options.status_code == 200
    assert options.json()["availability"] == "nest_full"
    assert options.json()["nest_capacity"]["remaining"] == 0
