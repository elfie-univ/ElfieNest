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


def test_unknown_executable_changes_fail_closed_without_local_main_escalation() -> None:
    plan = build_plan(["new_runtime_surface.py"], "commit")

    assert plan["effective_stage"] == "push"
    assert plan["full"] is True
    assert plan["unknown_paths"] == ["new_runtime_surface.py"]
    assert all(plan["capabilities"].values())


def test_source_changes_use_the_mirrored_test_directory_when_available() -> None:
    plan = build_plan(["app/features/setup/service.py"], "commit")

    assert plan["effective_stage"] == "commit"
    assert "test/app/features/setup" in plan["tests"]


def test_non_executable_documentation_stays_at_commit_tier() -> None:
    plan = build_plan(["docs/developer/engineering/testing.md"], "commit")

    assert plan["effective_stage"] == "commit"
    assert plan["tests"] == []


def test_toolchain_manifests_select_full_premerge_lanes() -> None:
    plan = build_plan(["docs/package.json"], "push")

    assert plan["effective_stage"] == "push"
    assert plan["full"] is True
    assert plan["capabilities"]["toolchain"] is True

    local_labels = {label for label, _command in _commands(plan, "base")}
    assert "dependency lock" in local_labels
    assert "documentation build" in local_labels
    assert "web frontend dependencies" not in local_labels
    assert "affected tests" not in local_labels


def test_frontend_change_selects_only_its_parallel_lane() -> None:
    plan = build_plan(
        ["app/interfaces/web/frontend/src/components/Example.tsx"], "push"
    )

    selected = {name for name, enabled in plan["capabilities"].items() if enabled}
    assert plan["effective_stage"] == "push"
    assert plan["full"] is False
    assert selected == {"security_fast", "web_frontend"}
    assert plan["tests"] == []

    commit_plan = build_plan(
        ["app/interfaces/web/frontend/src/components/Example.tsx"], "commit"
    )
    local_labels = {label for label, _command in _commands(commit_plan, "base")}
    assert "web frontend dependencies" not in local_labels
    assert "web frontend tests" not in local_labels


def test_python_change_selects_remote_tests_and_quality_in_parallel() -> None:
    plan = build_plan(["app/features/setup/service.py"], "push")

    assert plan["capabilities"]["python_bundles"] is True
    assert plan["capabilities"]["python_quality"] is True
    assert plan["capabilities"]["runtime_smoke"] is False


def test_nested_agent_rules_are_governance_not_local_product_work() -> None:
    plan = build_plan(["app/interfaces/web/frontend/AGENTS.md"], "push")

    assert plan["full"] is True
    assert plan["capabilities"]["web_frontend"] is True
    assert plan["direct_capabilities"]["governance"] is True
    assert plan["direct_capabilities"]["architecture"] is True
    assert plan["direct_capabilities"]["web_frontend"] is False

    local_labels = {label for label, _command in _commands(plan, "base")}
    assert "governance change policy" in local_labels
    assert "architecture tests" in local_labels
    assert "web frontend dependencies" not in local_labels


def test_router_and_workflow_changes_cannot_approve_themselves() -> None:
    plan = build_plan(
        [
            ".github/workflows/ci.yml",
            "scripts/architecture/validation_plan.py",
        ],
        "push",
    )

    assert plan["full"] is True
    assert plan["capabilities"]["governance"] is True
    assert all(plan["capabilities"].values())
    local_labels = {label for label, _command in _commands(plan, "base")}
    assert "governance change policy" in local_labels
    assert "architecture tests" in local_labels
    assert "web frontend dependencies" not in local_labels
    assert "affected tests" not in local_labels

    governance_command = next(
        command
        for label, command in _commands(plan, "base")
        if label == "governance change policy"
    )
    assert governance_command[-3:] == [
        "--paths",
        ".github/workflows/ci.yml",
        "scripts/architecture/validation_plan.py",
    ]


def test_bootstrap_and_closure_governance_fail_closed() -> None:
    bootstrap = build_plan(["scripts/bootstrap_runtime_dependencies.sh"], "push")
    closure = build_plan(["task-closure-lifecycle.json"], "push")

    assert bootstrap["full"] is True
    assert bootstrap["capabilities"]["toolchain"] is True
    assert bootstrap["capabilities"]["release"] is True
    assert closure["full"] is True
    assert closure["capabilities"]["governance"] is True


def test_changed_paths_excludes_gate_generated_coverage_report(monkeypatch) -> None:
    commands = []

    def fake_run_lines(command):
        commands.append(command)
        return ["coverage.xml", "app/features/setup/service.py"]

    monkeypatch.setattr(
        validation_plan,
        "_run_lines",
        fake_run_lines,
    )

    assert validation_plan.changed_paths("base") == ["app/features/setup/service.py"]
    assert "--no-renames" in commands[0]


def test_manifest_exports_single_line_github_outputs(tmp_path: Path) -> None:
    output = tmp_path / "github-output"
    plan = build_plan(
        ["app/interfaces/web/frontend/src/components/Example.tsx"], "push"
    )

    validation_plan._write_github_outputs(output, plan)

    values = dict(
        line.split("=", maxsplit=1)
        for line in output.read_text(encoding="utf-8").splitlines()
    )
    assert values["router_version"] == validation_plan.MANIFEST_SCHEMA_VERSION
    assert values["web_frontend"] == "true"
    assert values["python_bundles"] == "false"
    assert values["python_quality"] == "false"
    assert json.loads(values["manifest_json"])["full"] is False


def test_ci_separates_candidate_merge_and_postsubmit_checks() -> None:
    workflow = (validation_plan.PROJECT_ROOT / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )

    assert "merge_group:" in workflow
    assert "name: elfienest/ci-gate" in workflow
    assert "name: elfienest/merge-gate" in workflow
    assert "needs: ci-gate" in workflow
    assert "CI_GATE_RESULT: ${{ needs.ci-gate.result }}" in workflow
    assert "if: github.event_name != 'merge_group'" in workflow
    assert "name: Release contract" in workflow
    assert 'require_lane release "$RELEASE_SELECTED" "$RELEASE_RESULT"' in workflow
    assert "name: Enforce main health quarantine" in workflow
    assert '"main-recovery" in labels' in workflow
    assert "name: Complete full backstop" in workflow
    assert "full-gate:" in workflow
    assert "python-quality:" in workflow
    assert "runtime-smoke:" in workflow
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "--stage full" in workflow
    assert "pre-commit run gitleaks --all-files" in workflow


def test_ci_uses_the_base_branch_router_and_fails_closed_during_bootstrap() -> None:
    workflow = (validation_plan.PROJECT_ROOT / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )

    assert "$base_sha:scripts/architecture/validation_plan.py" in workflow
    assert "base branch predates the trusted router; selecting every lane" in workflow
    assert "affected-v(1|2)" in workflow
    assert 'MANIFEST_SCHEMA_VERSION = "affected-v2"' in workflow


def test_command_selection_keeps_g1_focused_and_adds_g2_quality() -> None:
    commit_plan = build_plan(["app/features/setup/service.py"], "commit")
    push_plan = build_plan(
        ["infrastructure/models/providers/request_profiles.py"], "commit"
    )

    commit_labels = {label for label, _command in _commands(commit_plan, "base")}
    push_labels = {label for label, _command in _commands(push_plan, "base")}
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


def test_full_reuses_backstop_but_rechecks_current_candidate(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(validation_gate, "changed_paths", lambda _base: ["source.py"])
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
            AssertionError("the complete full gate must not run")
        ),
    )

    result = validation_gate.run_stage("full", "base", tmp_path, False)

    assert result == 0
    assert labels == ["diff format"]
    assert stored == [
        (
            "exact-key",
            "full",
            "base",
            {"reused_from": "backstop-key"},
        )
    ]


def test_full_runs_and_records_backstop_when_execution_input_changes(
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

    result = validation_gate.run_stage("full", "base", tmp_path, False)

    assert result == 0
    assert calls[0][:4] == [
        "bash",
        "scripts/pre_submit_gate.sh",
        "--stage",
        "full",
    ]
    assert stored == [
        ("backstop-key", "full-backstop", "base", {}),
        ("exact-key", "full", "base", {}),
    ]


def test_full_no_cache_reaches_direct_backstop_without_reusing_bundles(
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

    result = validation_gate.run_stage("full", "base", tmp_path, True)

    assert result == 0
    assert "--direct-full" in calls[0]
    assert "--no-cache" in calls[0]


def test_exact_full_cache_hit_rechecks_current_candidate_before_reuse(
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

    result = validation_gate.run_stage("full", "base", tmp_path, False)

    assert result == 1
    assert calls
