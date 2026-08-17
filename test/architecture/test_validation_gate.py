"""Behavior tests for the tiered validation planner and pass cache."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import scripts.architecture.validation_cache as validation_cache
import scripts.architecture.validation_gate as validation_gate
import scripts.architecture.validation_plan as validation_plan
from scripts.architecture.validation_cache import (
    backstop_fingerprint,
    cache_hit,
    cache_store,
)
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
        label for label, _command in _commands(commit_plan, "base")
    }
    push_labels = {
        label for label, _command in _commands(push_plan, "base")
    }
    assert "affected tests" in commit_labels
    assert "quality baseline" not in commit_labels
    assert "affected tests" in push_labels
    assert "quality baseline" in push_labels

    affected_command = next(
        command
        for label, command in _commands(commit_plan, "base")
        if label == "affected tests"
    )
    assert "scripts/architecture/validation_test_bundles.py" in affected_command
    assert "--selectors" in affected_command


def test_no_cache_is_forwarded_to_the_controlled_affected_test_runner() -> None:
    plan = build_plan(["app/features/setup/service.py"], "commit")

    affected_command = next(
        command
        for label, command in _commands(plan, "base", no_cache=True)
        if label == "affected tests"
    )

    assert affected_command[-1] == "--no-cache"


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


def test_cache_runtime_fingerprint_ignores_ephemeral_codex_path_entries(
    monkeypatch,
) -> None:
    stable_path = os.pathsep.join(("/usr/bin", "/opt/bin"))
    monkeypatch.setenv(
        "PATH",
        os.pathsep.join((stable_path, "/Users/test/.codex/tmp/arg0/codex-arg0-first")),
    )
    first = validation_cache._runtime_fingerprint_values()

    monkeypatch.setenv(
        "PATH",
        os.pathsep.join((stable_path, "/Users/test/.codex/tmp/arg0/codex-arg0-second")),
    )
    second = validation_cache._runtime_fingerprint_values()

    assert first == second

    monkeypatch.setenv("PATH", os.pathsep.join((stable_path, "/custom/tooling")))
    assert validation_cache._runtime_fingerprint_values() != first


def test_backstop_fingerprint_includes_every_changed_path(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(validation_cache, "PROJECT_ROOT", tmp_path)
    source = tmp_path / "changed.py"
    guide = tmp_path / "guide.md"
    source.write_text("value = 1\n", encoding="utf-8")
    guide.write_text("first\n", encoding="utf-8")
    paths = ["changed.py", "guide.md"]

    first = backstop_fingerprint("base", paths)
    source.write_text("value = 2\n", encoding="utf-8")
    after_source = backstop_fingerprint("base", paths)
    source.write_text("value = 1\n", encoding="utf-8")
    guide.write_text("second\n", encoding="utf-8")
    after_documentation = backstop_fingerprint("base", paths)

    assert after_source != first
    assert after_documentation != first


def test_main_reuses_backstop_but_rechecks_current_candidate(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        validation_gate, "changed_paths", lambda _base: ["source.py"]
    )
    monkeypatch.setattr(
        validation_gate,
        "candidate_fingerprint",
        lambda _base, _stage, _paths: "exact-key",
    )
    monkeypatch.setattr(
        validation_gate,
        "backstop_fingerprint",
        lambda _base, _paths: "backstop-key",
    )
    monkeypatch.setattr(
        validation_gate,
        "cache_hit",
        lambda _root, key: key == "backstop-key",
    )
    labels = []
    monkeypatch.setattr(
        validation_gate,
        "_command",
        lambda label, _command, _env: labels.append(label) or 0,
    )
    stored = []
    monkeypatch.setattr(
        validation_gate,
        "cache_store",
        lambda _root, key, stage, base, **metadata: stored.append(
            (key, stage, base, metadata)
        ),
    )
    monkeypatch.setattr(
        validation_gate.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("the complete main gate must not run")
        ),
    )

    result = validation_gate.run_stage(
        "main", "base", tmp_path, False
    )

    assert result == 0
    assert labels == ["diff format"]
    assert stored == [
        (
            "exact-key",
            "main",
            "base",
            {"reused_from": "backstop-key"},
        )
    ]


def test_main_runs_and_records_full_backstop_when_execution_input_changes(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(validation_gate, "changed_paths", lambda _base: ["changed.py"])
    monkeypatch.setattr(
        validation_gate,
        "candidate_fingerprint",
        lambda _base, _stage, _paths: "exact-key",
    )
    monkeypatch.setattr(
        validation_gate,
        "backstop_fingerprint",
        lambda _base, _paths: "backstop-key",
    )
    monkeypatch.setattr(validation_gate, "cache_hit", lambda _root, _key: False)
    calls = []
    monkeypatch.setattr(
        validation_gate.subprocess,
        "run",
        lambda command, **_kwargs: (
            calls.append(command) or SimpleNamespace(returncode=0)
        ),
    )
    stored = []
    monkeypatch.setattr(
        validation_gate,
        "cache_store",
        lambda _root, key, stage, base, **metadata: stored.append(
            (key, stage, base, metadata)
        ),
    )

    result = validation_gate.run_stage(
        "main", "base", tmp_path, False
    )

    assert result == 0
    assert calls[0][:4] == [
        "bash",
        "scripts/pre_submit_gate.sh",
        "--stage",
        "main",
    ]
    assert stored == [
        ("backstop-key", "main-backstop", "base", {}),
        ("exact-key", "main", "base", {}),
    ]


def test_main_no_cache_reaches_direct_backstop_without_reusing_bundles(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(validation_gate, "changed_paths", lambda _base: ["changed.py"])
    monkeypatch.setattr(
        validation_gate,
        "candidate_fingerprint",
        lambda _base, _stage, _paths: "exact-key",
    )
    monkeypatch.setattr(
        validation_gate, "backstop_fingerprint", lambda _base, _paths: "backstop-key"
    )
    calls = []
    monkeypatch.setattr(
        validation_gate.subprocess,
        "run",
        lambda command, **_kwargs: (
            calls.append(command) or SimpleNamespace(returncode=0)
        ),
    )

    result = validation_gate.run_stage(
        "main", "base", tmp_path, True
    )

    assert result == 0
    assert "--direct-main" in calls[0]
    assert "--no-cache" in calls[0]


def test_exact_main_cache_hit_rechecks_current_candidate_before_reuse(
    tmp_path: Path, monkeypatch
) -> None:
    changed = iter((["source.py"], ["source.py", "new.py"], ["source.py", "new.py"]))
    monkeypatch.setattr(validation_gate, "changed_paths", lambda _base: next(changed))
    monkeypatch.setattr(
        validation_gate,
        "candidate_fingerprint",
        lambda _base, _stage, paths: "exact-key" if len(paths) == 1 else "current-key",
    )
    monkeypatch.setattr(
        validation_gate,
        "backstop_fingerprint",
        lambda _base, _paths: "backstop-key",
    )
    monkeypatch.setattr(
        validation_gate,
        "cache_hit",
        lambda _root, key: key == "exact-key",
    )
    calls = []
    monkeypatch.setattr(
        validation_gate.subprocess,
        "run",
        lambda command, **_kwargs: (
            calls.append(command) or SimpleNamespace(returncode=1)
        ),
    )

    result = validation_gate.run_stage(
        "main", "base", tmp_path, False
    )

    assert result == 1
    assert calls
