"""Behavior tests for the tiered validation planner and pass cache."""

from __future__ import annotations

import json
from pathlib import Path

import scripts.architecture.validation_cache as validation_cache
import scripts.architecture.validation_plan as validation_plan
from scripts.architecture.validation_cache import cache_hit, cache_store
from scripts.architecture.validation_gate import _commands, build_plan


def test_provider_changes_select_the_affected_suite_at_push_tier() -> None:
    plan = build_plan(["infrastructure/models/providers/request_profiles.py"], "commit")

    assert plan["effective_stage"] == "push"
    assert "test/infrastructure/models/test_provider_catalog.py" in plan["tests"]
    assert (
        "test/app/interfaces/api/v1/admin/model_providers/test_routes.py"
        in plan["tests"]
    )


def test_unknown_executable_changes_escalate_to_main() -> None:
    plan = build_plan(["new_runtime_surface.py"], "commit")

    assert plan["effective_stage"] == "main"
    assert any("unknown executable" in reason for reason in plan["reasons"])


def test_source_changes_use_the_mirrored_test_directory_when_available() -> None:
    plan = build_plan(["app/features/setup/service.py"], "commit")

    assert plan["effective_stage"] == "commit"
    assert "test/app/features/setup" in plan["tests"]


def test_non_executable_documentation_stays_at_commit_tier() -> None:
    plan = build_plan(["docs/developer/engineering/testing.md"], "commit")

    assert plan["effective_stage"] == "commit"
    assert plan["tests"] == []


def test_task_matrix_metadata_does_not_escalate_a_product_change() -> None:
    plan = build_plan(
        ["task-closure.json", "infrastructure/models/providers/request_profiles.py"],
        "commit",
    )

    assert plan["effective_stage"] == "push"
    assert not any("task-closure.json" in reason for reason in plan["reasons"])


def test_toolchain_manifests_escalate_to_main() -> None:
    plan = build_plan(["docs/package.json"], "push")

    assert plan["effective_stage"] == "main"


def test_changed_paths_excludes_gate_generated_coverage_report(monkeypatch) -> None:
    monkeypatch.setattr(
        validation_plan,
        "_run_lines",
        lambda _command: ["coverage.xml", "app/features/setup/service.py"],
    )

    assert validation_plan.changed_paths("base") == ["app/features/setup/service.py"]


def test_command_selection_keeps_g1_focused_and_adds_g2_quality() -> None:
    commit_plan = build_plan(["app/features/setup/service.py"], "commit")
    push_plan = build_plan(
        ["infrastructure/models/providers/request_profiles.py"], "commit"
    )

    commit_labels = {
        label for label, _command in _commands(commit_plan, "base", "task-closure.json")
    }
    push_labels = {
        label for label, _command in _commands(push_plan, "base", "task-closure.json")
    }
    assert "affected tests" in commit_labels
    assert "quality baseline" not in commit_labels
    assert "affected tests" in push_labels
    assert "quality baseline" in push_labels


def test_cache_accepts_only_atomic_pass_records(tmp_path: Path) -> None:
    key = "a" * 64
    cache_store(tmp_path, key, "commit", "base-sha")

    assert cache_hit(tmp_path, key)
    record = json.loads((tmp_path / f"{key}.json").read_text(encoding="utf-8"))
    assert record == {
        "base_sha": "base-sha",
        "key": key,
        "result": "passed",
        "stage": "commit",
    }

    record["result"] = "failed"
    (tmp_path / f"{key}.json").write_text(json.dumps(record), encoding="utf-8")
    assert not cache_hit(tmp_path, key)


def test_candidate_fingerprint_changes_when_candidate_content_changes(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(validation_cache, "PROJECT_ROOT", tmp_path)
    candidate = tmp_path / "changed.py"
    candidate.write_text("value = 1\n", encoding="utf-8")
    first = validation_cache.candidate_fingerprint("base", "commit", ["changed.py"])

    candidate.write_text("value = 2\n", encoding="utf-8")
    second = validation_cache.candidate_fingerprint("base", "commit", ["changed.py"])

    assert first != second
