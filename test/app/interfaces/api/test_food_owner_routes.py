from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from ai_runtime.food.evidence import ModelEvidenceStore
from ai_runtime.food.planner import ModelEvidence
from app.infrastructure.persistence.store import init_db
from app.interfaces.api.app import create_app

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
        patch(
            "app.interfaces.api.food_owner_routes._FOOD_CATALOG_PATH", paths["catalog"]
        ),
        patch(
            "app.interfaces.api.food_owner_routes._FOOD_HISTORY_DIR", paths["history"]
        ),
        patch(
            "app.interfaces.api.food_owner_routes._MODEL_EVIDENCE_PATH",
            paths["evidence"],
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
    preview_data = preview.json()
    assert preview_data["has_changes"] is True
    assert preview_data["generation_sources"] == ["rules"]
    assert preview_data["current"]["foods"] == {}
    assert rejected.status_code == 409
    assert not paths["catalog"].exists()

    applied = client.post(
        "/api/owner/runtime/foods/update-apply",
        json={
            "confirm": True,
            "candidate": preview_data["candidate"],
            "base_catalog_fingerprint": preview_data["base_catalog_fingerprint"],
        },
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
        json={
            "confirm": True,
            "candidate": preview["candidate"],
            "base_catalog_fingerprint": preview["base_catalog_fingerprint"],
        },
        headers=headers,
    )
    assert applied.status_code == 200, applied.text

    stale = dict(preview["candidate"])
    stale["source_fingerprint"] = "stale"
    rejected = client.post(
        "/api/owner/runtime/foods/update-apply",
        json={
            "confirm": True,
            "candidate": stale,
            "base_catalog_fingerprint": preview["base_catalog_fingerprint"],
        },
        headers=headers,
    )
    assert rejected.status_code == 409


def test_confirmed_apply_without_a_preview_candidate_is_rejected(client, paths):
    headers = auth(client)

    response = client.post(
        "/api/owner/runtime/foods/update-apply",
        json={"confirm": True},
        headers=headers,
    )

    assert response.status_code == 422
    assert not paths["catalog"].exists()


def test_manual_edit_invalidates_an_older_preview(client):
    headers = auth(client)
    preview = client.post(
        "/api/owner/runtime/foods/update-preview",
        json={"use_llm": False},
        headers=headers,
    ).json()
    edited = client.put(
        "/api/owner/runtime/foods/standard",
        json={
            "display_name": "标准粮",
            "description": "后续人工调整",
            "primary": {"model": "ollama/local"},
        },
        headers=headers,
    )

    applied = client.post(
        "/api/owner/runtime/foods/update-apply",
        json={
            "confirm": True,
            "candidate": preview["candidate"],
            "base_catalog_fingerprint": preview["base_catalog_fingerprint"],
        },
        headers=headers,
    )

    assert edited.status_code == 200
    assert applied.status_code == 409
    assert "已过期" in applied.json()["detail"]


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


def test_food_api_rejects_a_bare_model_reference(client):
    headers = auth(client)
    response = client.put(
        "/api/owner/runtime/foods/standard",
        json={
            "display_name": "标准粮",
            "description": "人工调整",
            "primary": {"model": "qwen2.5:0.5b"},
        },
        headers=headers,
    )

    assert response.status_code == 422
    assert "provider_id/model_id" in response.json()["detail"]


def test_food_edit_round_trips_every_execution_role(client):
    headers = auth(client)
    response = client.put(
        "/api/owner/runtime/foods/standard",
        json={
            "display_name": "标准粮",
            "description": "四角色人工配置",
            "primary": {"model": "ollama/primary", "reasoning_profile": "balanced"},
            "deep": {"model": "ollama/deep", "reasoning_profile": "deep"},
            "vision": {"model": "ollama/vision", "reasoning_profile": "balanced"},
            "verifier": {"model": "ollama/verifier", "reasoning_profile": "verify"},
            "technical_fallbacks": [
                {"model": "ollama/fallback", "reasoning_profile": "low"}
            ],
        },
        headers=headers,
    )

    assert response.status_code == 200, response.text
    food = response.json()["food"]
    assert food["primary"]["model"] == "ollama/primary"
    assert food["deep"]["model"] == "ollama/deep"
    assert food["vision"]["model"] == "ollama/vision"
    assert food["verifier"]["model"] == "ollama/verifier"
    assert food["technical_fallbacks"][0]["model"] == "ollama/fallback"
    assert food["local_only"] is True


def test_custom_food_package_keeps_stable_id_when_renamed(client):
    headers = auth(client)
    created = client.post(
        "/api/owner/runtime/foods/",
        json={
            "display_name": "日常套餐",
            "description": "默认使用",
            "primary": {"model": "ollama/local"},
        },
        headers=headers,
    )

    assert created.status_code == 201, created.text
    food_id = created.json()["food"]["key"]
    assert food_id.startswith("food_")
    assert created.json()["catalog"]["default_food"] == food_id
    assert created.json()["food"]["local_only"] is True

    renamed = client.put(
        f"/api/owner/runtime/foods/{food_id}",
        json={
            "key": "food_should_not_replace_identity",
            "display_name": "改名后的日常套餐",
            "description": "默认使用",
            "primary": {"model": "ollama/local"},
        },
        headers=headers,
    )

    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["food"]["key"] == food_id
    assert renamed.json()["food"]["display_name"] == "改名后的日常套餐"


def test_owner_can_choose_global_fallback_and_cannot_delete_selected_food(client):
    headers = auth(client)
    first = client.post(
        "/api/owner/runtime/foods/",
        json={"display_name": "常用粮", "primary": {"model": "ollama/local"}},
        headers=headers,
    ).json()["food"]["key"]
    second = client.post(
        "/api/owner/runtime/foods/",
        json={"display_name": "保底粮", "primary": {"model": "cloud/cheap"}},
        headers=headers,
    ).json()["food"]["key"]

    selected = client.put(
        "/api/owner/runtime/foods/settings",
        json={"default_food": first, "fallback_food": second},
        headers=headers,
    )

    assert selected.status_code == 200, selected.text
    assert selected.json()["catalog"]["default_food"] == first
    assert selected.json()["catalog"]["fallback_food"] == second
    assert selected.json()["warnings"] == ["所选保底粮包含远程模型，断网时可能不可用"]
    rejected = client.delete(
        f"/api/owner/runtime/foods/{second}",
        headers=headers,
    )
    assert rejected.status_code == 409
