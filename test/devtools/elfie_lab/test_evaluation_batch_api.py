from __future__ import annotations

import json
import time

import pytest

from app.features.configuration.food import StoredFoodPackage
from infrastructure.persistence.food import SQLiteFoodAdapter
from infrastructure.persistence.nest_db.store import init_db
from test.devtools.elfie_lab.food_test_helpers import seed_mock_food


def _create_elfie(client) -> str:
    response = client.post(
        "/api/elfies",
        json={
            "name": "小岚",
            "species_id": "fox",
            "age_years": 2.0,
            "description": "批量评测测试精灵",
            "appearance_description": "赤色尾巴",
            "personality_description": "好奇但克制",
        },
    )
    assert response.status_code == 201
    return str(response.json()["elfie_id"])


def _seed_second_food(runtime) -> None:
    database = runtime / "nest.db"
    init_db(str(database))
    SQLiteFoodAdapter(database).create_package(
        StoredFoodPackage(
            food_id="mock_alt",
            display_name="测试粮 B",
            primary_model="ollama/elfie-mock",
        )
    )


def test_code_branch_endpoint_returns_named_refs(tmp_path, client_for) -> None:
    from devtools.elfie_lab.app import create_app

    runtime = tmp_path / "runtime"
    seed_mock_food(runtime)
    client = client_for(create_app(str(tmp_path / "data"), str(runtime)))

    response = client.get("/api/evaluations/code-branches")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["current_ref"]
    assert any(item["is_current"] for item in payload["items"])
    assert all("name" in item and "is_current" in item for item in payload["items"])


def test_code_pair_runs_named_branches_with_shared_fixture(
    tmp_path, client_for
) -> None:
    from devtools.elfie_lab.app import create_app

    runtime = tmp_path / "runtime"
    seed_mock_food(runtime)
    client = client_for(create_app(str(tmp_path / "data"), str(runtime)))
    elfie_id = _create_elfie(client)
    code_branches = client.get("/api/evaluations/code-branches")
    assert code_branches.status_code == 200, code_branches.text
    current_ref = code_branches.json()["current_ref"]
    other_ref = next(
        (
            item["name"]
            for item in code_branches.json()["items"]
            if item["name"] != current_ref
        ),
        None,
    )
    if other_ref is None:
        pytest.skip("代码分支对比至少需要两个可解析的不同引用")

    response = client.post(
        "/api/evaluations/batches/paired",
        json={
            "elfie_id": elfie_id,
            "suite": "quick",
            "comparison_variable": "code",
            "food_key_b": "mock",
            "judge_subscription_id": "mock",
            "code_ref_a": current_ref,
            "code_ref_b": other_ref,
            "title": "代码分支验证",
        },
    )
    assert response.status_code == 202, response.text
    batch = _wait_for_batch(client, response.json()["batch"]["batch_id"])

    assert batch["batch"]["status"] in {"completed", "partial_failed"}
    assert [item["source_ref"] for item in batch["reports"]] == [current_ref, other_ref]
    assert batch["batch"]["fixture_sha256"] == batch["reports"][0]["fixture_sha256"]


def _wait_for_batch(client, batch_id: str):
    deadline = time.monotonic() + 60
    last = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/evaluations/batches/{batch_id}")
        assert response.status_code == 200, response.text
        last = response.json()
        if last["batch"]["status"] in {"completed", "partial_failed", "failed"}:
            return last
        time.sleep(0.05)
    raise AssertionError(f"batch did not finish: {last}")


def test_food_pair_freezes_one_fixture_and_persists_strict_comparison(
    tmp_path,
    client_for,
) -> None:
    from devtools.elfie_lab.app import create_app

    runtime = tmp_path / "runtime"
    seed_mock_food(runtime)
    _seed_second_food(runtime)
    client = client_for(create_app(str(tmp_path / "data"), str(runtime)))
    elfie_id = _create_elfie(client)

    response = client.post(
        "/api/evaluations/batches/paired",
        json={
            "elfie_id": elfie_id,
            "suite": "quick",
            "comparison_variable": "food",
            "food_key_a": "mock",
            "food_key_b": "mock_alt",
            "judge_subscription_id": "mock",
            "purpose": "验证同一快照下的粮食差异",
        },
    )
    assert response.status_code == 202, response.text
    batch = _wait_for_batch(client, response.json()["batch"]["batch_id"])

    assert batch["batch"]["status"] == "completed"
    assert batch["batch"]["comparison_artifact_id"]
    assert len(batch["reports"]) == 2
    report_a, report_b = batch["reports"]
    assert report_a["fixture_snapshot_id"] == report_b["fixture_snapshot_id"]
    assert report_a["fixture_sha256"] == report_b["fixture_sha256"]
    assert report_a["test_plan_sha256"] == report_b["test_plan_sha256"]
    assert report_a["source_snapshot_sha256"] == report_b["source_snapshot_sha256"]
    assert report_a["food_spec_sha256"] != report_b["food_spec_sha256"]
    assert report_a["execution_rules"]

    comparison = client.post(
        "/api/evaluations/comparisons",
        json={
            "report_a_id": report_a["run_id"],
            "report_b_id": report_b["run_id"],
        },
    )
    assert comparison.status_code == 200, comparison.text
    assert comparison.json()["grade"] == "strict"
    assert comparison.json()["comparison_variable"] == "food"
    assert comparison.json()["report_a_coverage"] >= 0
    assert comparison.json()["report_b_coverage"] >= 0
    assert "compatibility_reasons" in comparison.json()

    listing = client.get("/api/evaluations")
    assert listing.status_code == 200
    assert listing.json()["items"][0]["batch"]["batch_id"] == batch["batch"]["batch_id"]


def test_single_batch_keeps_soft_scenarios_as_evidence_ready(
    tmp_path,
    client_for,
) -> None:
    from devtools.elfie_lab.app import create_app

    runtime = tmp_path / "runtime"
    seed_mock_food(runtime)
    _seed_second_food(runtime)
    client = client_for(create_app(str(tmp_path / "data"), str(runtime)))
    elfie_id = _create_elfie(client)

    response = client.post(
        "/api/evaluations/batches/single",
        json={
            "elfie_id": elfie_id,
            "suite": "quick",
            "food_key": "mock",
            "judge_subscription_id": "mock",
            "judge_model": "elfie-mock",
            "purpose": "查看当前候选的绝对证据",
        },
    )
    assert response.status_code == 202, response.text
    batch = _wait_for_batch(client, response.json()["batch"]["batch_id"])
    report = batch["reports"][0]

    assert batch["batch"]["status"] == "completed"
    scenario_statuses = {item["status"] for item in report["scenarios"]}
    assert "evidence_ready" in scenario_statuses
    assert report["verdict"] in {"evidence_ready", "failed"}
    assert report["fixture_snapshot_id"]
    assert report["fixture_captured_at"]
    assert report["judge_model"] == "ollama/elfie-mock"
    assert report["overall_score"] is not None
    assert report["score_coverage"] > 0
    assert report["validity"] in {"valid", "incomplete", "p0_blocked"}
    assert all(item["input_messages"] for item in report["scenarios"])
    assert all(item["attempt_id"] for item in report["scenarios"])
    assert report["total_model_calls"] >= 0
    evidence = client.get(f"/api/evaluations/reports/{report['run_id']}/evidence")
    assert evidence.status_code == 200, evidence.text
    assert evidence.json()["run_id"] == report["run_id"]
    assert evidence.json()["episodes"]
    assert "api_key" not in evidence.text.lower()

    repeated_response = client.post(
        "/api/evaluations/batches/single",
        json={
            "elfie_id": elfie_id,
            "suite": "quick",
            "food_key": "mock",
            "judge_subscription_id": "mock",
            "purpose": "重复运行相同候选",
        },
    )
    assert repeated_response.status_code == 202, repeated_response.text
    repeated = _wait_for_batch(
        client,
        repeated_response.json()["batch"]["batch_id"],
    )["reports"][0]
    comparison = client.post(
        "/api/evaluations/comparisons",
        json={
            "report_a_id": report["run_id"],
            "report_b_id": repeated["run_id"],
        },
    )
    assert comparison.status_code == 200, comparison.text
    assert comparison.json()["grade"] == "observational"
    assert comparison.json()["differing_fields"] == []
    assert "重复运行" in comparison.json()["warnings"][0]

    missing_code_refs = client.post(
        "/api/evaluations/batches/paired",
        json={
            "elfie_id": elfie_id,
            "suite": "quick",
            "comparison_variable": "code",
            "food_key_b": "mock",
            "judge_subscription_id": "mock",
            "code_ref_a": "HEAD",
            "purpose": "代码对比必须选择两个分支",
        },
    )
    assert missing_code_refs.status_code == 422
    assert "代码分支 A 和 B" in missing_code_refs.text

    first_page = client.get("/api/evaluations?limit=1&offset=0")
    second_page = client.get("/api/evaluations?limit=1&offset=1")
    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert first_page.json()["total"] == 2
    assert (
        first_page.json()["items"][0]["batch"]["batch_id"]
        != second_page.json()["items"][0]["batch"]["batch_id"]
    )

    empty_future = client.get("/api/evaluations?created_after=2100-01-01T00%3A00%3A00Z")
    assert empty_future.status_code == 200
    assert empty_future.json()["total"] == 0
    assert empty_future.json()["items"] == []


def test_batch_listing_skips_an_incompatible_stored_report(
    tmp_path, client_for
) -> None:
    """One stale developer report must not take down the whole report library."""

    from devtools.elfie_lab.app import create_app

    runtime = tmp_path / "runtime"
    seed_mock_food(runtime)
    client = client_for(create_app(str(tmp_path / "data"), str(runtime)))
    elfie_id = _create_elfie(client)
    response = client.post(
        "/api/evaluations/batches/single",
        json={
            "elfie_id": elfie_id,
            "suite": "quick",
            "food_key": "mock",
            "judge_subscription_id": "mock",
            "purpose": "制造一份随后变旧的开发报告",
        },
    )
    assert response.status_code == 202, response.text
    batch = _wait_for_batch(client, response.json()["batch"]["batch_id"])
    run_id = batch["reports"][0]["run_id"]
    report_path = next(tmp_path.glob(f"**/{run_id}.json"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["judge_food_key"] = report.pop("judge_subscription_id")
    report_path.write_text(json.dumps(report), encoding="utf-8")

    listing = client.get("/api/evaluations")

    assert listing.status_code == 200, listing.text
    assert listing.json()["items"] == []
