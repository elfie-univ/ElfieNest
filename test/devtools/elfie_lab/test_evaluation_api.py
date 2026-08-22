from __future__ import annotations

import time
from typing import Any, Dict

from test.devtools.elfie_lab.food_test_helpers import seed_mock_food


def _create_elfie(client) -> str:
    response = client.post(
        "/api/elfies",
        json={
            "name": "小岚",
            "species_id": "fox",
            "age_years": 2.0,
            "description": "版本评测使用的合成测试精灵",
            "appearance_description": "赤色尾巴，左耳尖有浅色毛",
            "personality_description": "好奇但克制，不确定时先澄清",
        },
    )
    assert response.status_code == 201
    return str(response.json()["elfie_id"])


def _wait_for_run(client, elfie_id: str, run_id: str) -> Dict[str, Any]:
    deadline = time.monotonic() + 60.0
    last_payload: Dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/elfies/{elfie_id}/evaluations/{run_id}")
        assert response.status_code == 200
        payload = response.json()
        last_payload = payload
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(
        f"evaluation run did not finish: {run_id}; last={last_payload}"
    )


def _start_quick_run(client, elfie_id: str) -> Dict[str, Any]:
    response = client.post(
        f"/api/elfies/{elfie_id}/evaluations",
        json={
            "suite": "quick",
            "food_key": "mock",
            "judge_food_key": "mock",
        },
    )
    assert response.status_code == 202, response.text
    return _wait_for_run(client, elfie_id, str(response.json()["run_id"]))


def test_evaluation_presets_are_product_facing_and_godot_optional(
    tmp_path, client_for
) -> None:
    from devtools.elfie_lab.app import create_app

    client = client_for(create_app(str(tmp_path / "data"), str(tmp_path / "runtime")))

    response = client.get("/api/evaluations/presets")

    assert response.status_code == 200
    payload = response.json()
    assert [item["key"] for item in payload["items"]] == ["quick", "standard"]
    assert payload["items"][0]["scenario_count"] == 3
    assert payload["items"][1]["scenario_count"] == 8
    assert all(item["requires_godot"] is False for item in payload["items"])
    assert "家族" not in str(payload)


def test_first_run_becomes_baseline_and_next_run_compares_against_it(
    tmp_path, client_for
) -> None:
    from devtools.elfie_lab.app import create_app

    runtime = tmp_path / "runtime"
    seed_mock_food(runtime)
    client = client_for(create_app(str(tmp_path / "data"), str(runtime)))
    elfie_id = _create_elfie(client)

    baseline = _start_quick_run(client, elfie_id)
    candidate = _start_quick_run(client, elfie_id)

    assert baseline["status"] == "completed"
    assert baseline["verdict"] == "baseline"
    assert baseline["is_baseline"] is True
    assert baseline["total_scenarios"] == 3
    assert baseline["completed_scenarios"] == 3
    assert len(baseline["source_snapshot_sha256"]) == 64
    assert baseline["food_model"] == "ollama/elfie-mock"
    assert baseline["judge_model"] == "ollama/elfie-mock"
    assert any("开发基线只是比较起点" in item for item in baseline["warnings"])
    assert candidate["status"] == "completed"
    assert candidate["baseline_run_id"] == baseline["run_id"]
    assert candidate["verdict"] == "incomplete"
    assert candidate["is_baseline"] is False
    assert len(candidate["scenarios"]) == 3
    assert {item["dimension"] for item in candidate["dimensions"]} >= {
        "identity_continuity",
        "memory_relationships",
    }

    history = client.get(f"/api/elfies/{elfie_id}/evaluations")
    assert history.status_code == 200
    assert history.json()["baseline_run_ids"]["quick"] == baseline["run_id"]
    assert [item["run_id"] for item in history.json()["items"]][:2] == [
        candidate["run_id"],
        baseline["run_id"],
    ]


def test_completed_run_can_be_selected_as_the_new_development_baseline(
    tmp_path, client_for
) -> None:
    from devtools.elfie_lab.app import create_app

    runtime = tmp_path / "runtime"
    seed_mock_food(runtime)
    client = client_for(create_app(str(tmp_path / "data"), str(runtime)))
    elfie_id = _create_elfie(client)
    _start_quick_run(client, elfie_id)
    candidate = _start_quick_run(client, elfie_id)

    response = client.post(
        f"/api/elfies/{elfie_id}/evaluations/{candidate['run_id']}/baseline"
    )

    assert response.status_code == 200
    assert response.json()["is_baseline"] is True
    history = client.get(f"/api/elfies/{elfie_id}/evaluations").json()
    assert history["baseline_run_ids"]["quick"] == candidate["run_id"]


def test_standard_run_covers_all_six_user_facing_dimensions(
    tmp_path, client_for
) -> None:
    from devtools.elfie_lab.app import create_app

    runtime = tmp_path / "runtime"
    seed_mock_food(runtime)
    client = client_for(create_app(str(tmp_path / "data"), str(runtime)))
    elfie_id = _create_elfie(client)

    response = client.post(
        f"/api/elfies/{elfie_id}/evaluations",
        json={
            "suite": "standard",
            "food_key": "mock",
            "judge_food_key": "mock",
        },
    )
    assert response.status_code == 202, response.text
    run = _wait_for_run(client, elfie_id, str(response.json()["run_id"]))

    assert run["status"] == "completed"
    assert run["total_scenarios"] == 8
    assert len(run["dimensions"]) == 6
    assert {item["dimension"] for item in run["dimensions"]} == {
        "identity_continuity",
        "understanding_reasoning",
        "memory_relationships",
        "emotion_energy",
        "autonomy_boundaries",
        "commitment_reliability",
    }


def test_evaluation_rejects_unknown_or_unconfigured_food(tmp_path, client_for) -> None:
    from devtools.elfie_lab.app import create_app

    client = client_for(create_app(str(tmp_path / "data"), str(tmp_path / "runtime")))
    elfie_id = _create_elfie(client)

    response = client.post(
        f"/api/elfies/{elfie_id}/evaluations",
        json={
            "suite": "quick",
            "food_key": "missing-food",
            "judge_food_key": "mock",
        },
    )

    assert response.status_code == 422
    assert "不存在" in response.json()["detail"]
