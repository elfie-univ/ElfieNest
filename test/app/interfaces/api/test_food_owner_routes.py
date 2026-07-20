from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.interfaces.api.app import create_app
from app.infrastructure.persistence.store import init_db
from ai_runtime.food.evidence import ModelEvidenceStore
from ai_runtime.food.planner import ModelEvidence

from ._helpers import create_test_owner


@pytest.fixture
def paths(tmp_path):
    return {
        "catalog": tmp_path / "foods.yaml",
        "history": tmp_path / "history",
        "evidence": tmp_path / "evidence.yaml",
    }


@pytest.fixture
def client(tmp_path, paths):
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_test_owner(db_path)
    ModelEvidenceStore(paths["evidence"]).merge(
        [
            ModelEvidence(
                "ollama/local",
                frozenset({"text", "reasoning"}),
                True,
                cost_grade=0,
                local=True,
            )
        ]
    )
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
        patch("app.interfaces.api.food_owner_routes._FOOD_CATALOG_PATH", paths["catalog"]),
        patch("app.interfaces.api.food_owner_routes._FOOD_HISTORY_DIR", paths["history"]),
        patch(
            "app.interfaces.api.food_owner_routes._MODEL_EVIDENCE_PATH", paths["evidence"]
        ),
    ):
        app = create_app(engine=None, db_path=db_path, ws_port=9876)
        with TestClient(app) as test_client:
            yield test_client


def auth(client):
    login = client.post(
        "/api/auth/login", data={"username": "owner", "password": "ownerchangeme"}
    )
    return {"X-CSRF-Token": login.headers["X-CSRF-Token"]}


def test_food_update_is_previewed_and_requires_confirmation(client, paths):
    headers = auth(client)

    status = client.get("/api/owner/runtime/foods/update-status", headers=headers)
    preview = client.post(
        "/api/owner/runtime/foods/update-preview",
        json={"use_llm": False},
        headers=headers,
    )
    rejected = client.post(
        "/api/owner/runtime/foods/update-apply",
        json={"confirm": False},
        headers=headers,
    )

    assert status.json()["update_available"] is True
    assert preview.json()["has_changes"] is True
    assert preview.json()["generation_sources"] == ["rules"]
    assert rejected.status_code == 409
    assert not paths["catalog"].exists()

    applied = client.post(
        "/api/owner/runtime/foods/update-apply",
        json={"confirm": True},
        headers=headers,
    )
    assert applied.status_code == 200
    assert paths["catalog"].exists()


def test_exact_preview_candidate_can_be_applied_but_stale_candidate_is_rejected(
    client,
):
    headers = auth(client)
    preview = client.post(
        "/api/owner/runtime/foods/update-preview",
        json={"use_llm": False},
        headers=headers,
    ).json()

    applied = client.post(
        "/api/owner/runtime/foods/update-apply",
        json={"confirm": True, "candidate": preview["candidate"]},
        headers=headers,
    )
    assert applied.status_code == 200, applied.text

    stale = dict(preview["candidate"])
    stale["source_fingerprint"] = "stale"
    rejected = client.post(
        "/api/owner/runtime/foods/update-apply",
        json={"confirm": True, "candidate": stale},
        headers=headers,
    )
    assert rejected.status_code == 409


def test_food_can_be_edited_without_separate_expert_mode(client):
    headers = auth(client)
    response = client.put(
        "/api/owner/runtime/foods/standard",
        json={
            "display_name": "标准粮",
            "description": "人工调整",
            "primary": {"model": "ollama/local"},
        },
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["food"]["source"] == "manual"
