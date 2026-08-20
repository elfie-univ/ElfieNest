"""Behavior tests for the tiered validation planner and pass cache."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.architecture.validation_cache as validation_cache
import scripts.architecture.validation_gate as validation_gate
import scripts.architecture.validation_plan as validation_plan
from scripts.architecture.validation_cache import (
    backstop_fingerprint,
    cache_hit,
    cache_store,
)
from scripts.architecture.validation_gate import _commands, build_plan


def _git(repository: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=repository,
        text=True,
    ).strip()


def _initialize_git_repository(repository: Path, files: dict[str, str]) -> str:
    _git(repository, "init")
    _git(repository, "config", "user.name", "Validation Gate Test")
    _git(repository, "config", "user.email", "validation-gate-test@localhost")
    for relative_path, content in files.items():
        path = repository / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(repository, "add", "--all")
    _git(repository, "commit", "-m", "base")
    return _git(repository, "rev-parse", "HEAD^{commit}")


def _fake_uv(tmp_path: Path, *, exit_code: int = 0) -> tuple[Path, Path]:
    executable = tmp_path / "fake-uv"
    log = tmp_path / "fake-uv.log"
    executable.write_text(
        f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {str(log)!r}\nexit {exit_code}\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable, log


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
        lambda _command: [
            "coverage.xml",
            "app/features/setup/service.py",
            "devtools/web/node_modules",
            "docs/node_modules/.modules.yaml",
        ],
    )

    assert validation_plan.changed_paths("base") == ["app/features/setup/service.py"]


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


def test_main_reuses_backstop_but_rechecks_current_candidate(
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
    monkeypatch.setattr(
        validation_gate,
        "prepare_format_fastlane",
        lambda *_args, **_kwargs: 0,
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

    result = validation_gate.run_stage("main", "base", tmp_path, False)

    assert result == 0
    assert labels == []
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
    monkeypatch.setattr(
        validation_gate,
        "prepare_format_fastlane",
        lambda *_args, **_kwargs: 0,
    )
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

    result = validation_gate.run_stage("main", "base", tmp_path, False)

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
    monkeypatch.setattr(
        validation_gate,
        "prepare_format_fastlane",
        lambda *_args, **_kwargs: 0,
    )
    calls = []
    monkeypatch.setattr(
        validation_gate.subprocess,
        "run",
        lambda command, **_kwargs: (
            calls.append(command) or SimpleNamespace(returncode=0)
        ),
    )

    result = validation_gate.run_stage("main", "base", tmp_path, True)

    assert result == 0
    assert "--direct-main" in calls[0]
    assert "--no-cache" in calls[0]


def test_main_key_change_stops_before_using_an_obsolete_lock(
    tmp_path: Path, monkeypatch
) -> None:
    changed = iter(
        (
            ["source.py"],
            ["source.py"],
            ["source.py", "new.py"],
            ["source.py", "new.py"],
        )
    )
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
    monkeypatch.setattr(
        validation_gate,
        "prepare_format_fastlane",
        lambda *_args, **_kwargs: 0,
    )
    calls = []
    monkeypatch.setattr(
        validation_gate.subprocess,
        "run",
        lambda command, **_kwargs: (
            calls.append(command) or SimpleNamespace(returncode=1)
        ),
    )

    result = validation_gate.run_stage("main", "base", tmp_path, False)

    assert result == 1
    assert calls == []


def test_focused_key_change_stops_before_using_an_obsolete_lock(
    tmp_path: Path, monkeypatch
) -> None:
    changed = iter((["source.py"], ["source.py"], ["source.py", "new.py"]))
    monkeypatch.setattr(validation_gate, "changed_paths", lambda _base: next(changed))
    monkeypatch.setattr(
        validation_gate,
        "candidate_fingerprint",
        lambda _base, _stage, paths: "initial-key" if len(paths) == 1 else "new-key",
    )
    monkeypatch.setattr(
        validation_gate,
        "prepare_format_fastlane",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        validation_gate,
        "_command",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("no check may run while holding an obsolete key lock")
        ),
    )

    result = validation_gate.run_stage("commit", "base", tmp_path, False)

    assert result == 1


def test_format_fix_scope_uses_only_existing_dirty_python_candidates(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(validation_gate, "PROJECT_ROOT", tmp_path)
    for relative_path in (
        "dirty.py",
        "untracked.pyi",
        "committed_only.py",
        "notes.md",
        "outside_candidate.py",
    ):
        (tmp_path / relative_path).write_text("value = 1\n", encoding="utf-8")

    fixable, mixed = validation_gate._format_fix_scope(
        [
            "dirty.py",
            "untracked.pyi",
            "committed_only.py",
            "notes.md",
            "deleted.py",
        ],
        [],
        ["dirty.py", "notes.md", "deleted.py", "outside_candidate.py"],
        ["untracked.pyi"],
    )

    assert fixable == ["dirty.py", "untracked.pyi"]
    assert mixed == []


def test_format_fix_scope_reports_mixed_staged_and_unstaged_python(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(validation_gate, "PROJECT_ROOT", tmp_path)
    (tmp_path / "mixed.py").write_text("value = 2\n", encoding="utf-8")
    (tmp_path / "staged.py").write_text("value = 3\n", encoding="utf-8")
    (tmp_path / "outside.py").write_text("value = 4\n", encoding="utf-8")

    fixable, mixed = validation_gate._format_fix_scope(
        ["mixed.py", "staged.py"],
        ["mixed.py", "staged.py", "outside.py"],
        ["mixed.py", "outside.py"],
        [],
    )

    assert fixable == []
    assert mixed == ["mixed.py"]


def test_prepare_format_fastlane_formats_only_dirty_and_untracked_python(
    tmp_path: Path, monkeypatch
) -> None:
    base = _initialize_git_repository(
        tmp_path,
        {
            "dirty.py": "value=1\n",
            "committed_only.py": "value=2\n",
            "deleted.py": "value=3\n",
            "notes.md": "before\n",
        },
    )
    (tmp_path / "dirty.py").write_text("value = 10\n", encoding="utf-8")
    (tmp_path / "new.py").write_text("value=20\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("after\n", encoding="utf-8")
    (tmp_path / "deleted.py").unlink()
    fake_uv, log = _fake_uv(tmp_path)
    monkeypatch.setattr(validation_gate, "PROJECT_ROOT", tmp_path)
    real_which = validation_gate.shutil.which
    monkeypatch.setattr(
        validation_gate.shutil,
        "which",
        lambda command: str(fake_uv) if command == "uv" else real_which(command),
    )

    result = validation_gate.prepare_format_fastlane(
        base,
        ["dirty.py", "new.py", "committed_only.py", "deleted.py", "notes.md"],
        fix_format=True,
        env=os.environ.copy(),
    )

    assert result == 0
    invocations = log.read_text(encoding="utf-8").splitlines()
    assert any(
        line == "run --no-sync ruff format dirty.py new.py" for line in invocations
    )
    write_invocations = [
        line
        for line in invocations
        if " ruff format " in f" {line} " and " format --check " not in f" {line} "
    ]
    assert write_invocations == ["run --no-sync ruff format dirty.py new.py"]


def test_prepare_format_fastlane_refuses_mixed_staged_and_unstaged_file(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    base = _initialize_git_repository(tmp_path, {"mixed.py": "value=1\n"})
    (tmp_path / "mixed.py").write_text("value=2\n", encoding="utf-8")
    _git(tmp_path, "add", "mixed.py")
    (tmp_path / "mixed.py").write_text("value=3\n", encoding="utf-8")
    fake_uv, log = _fake_uv(tmp_path)
    monkeypatch.setattr(validation_gate, "PROJECT_ROOT", tmp_path)
    real_which = validation_gate.shutil.which
    monkeypatch.setattr(
        validation_gate.shutil,
        "which",
        lambda command: str(fake_uv) if command == "uv" else real_which(command),
    )

    result = validation_gate.prepare_format_fastlane(
        base,
        ["mixed.py"],
        fix_format=True,
        env=os.environ.copy(),
    )

    assert result == 1
    assert "mixed.py" in capsys.readouterr().err
    assert not log.exists()


def test_g3_escalation_runs_format_fastlane_before_complete_main_gate(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        validation_gate, "changed_paths", lambda _base: ["new_runtime_surface.py"]
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
    events = []
    monkeypatch.setattr(
        validation_gate,
        "prepare_format_fastlane",
        lambda *_args, **_kwargs: events.append("format") or 0,
    )
    monkeypatch.setattr(
        validation_gate.subprocess,
        "run",
        lambda command, **_kwargs: (
            events.append("main") or SimpleNamespace(returncode=0)
        ),
    )

    result = validation_gate.run_stage(
        "commit",
        "base",
        tmp_path,
        True,
        fix_format=True,
    )

    assert result == 0
    assert events == ["format", "main"]


@pytest.mark.parametrize(
    "changed_path",
    ["app/features/setup/service.py", "new_runtime_surface.py"],
)
def test_format_failure_stops_before_focused_tests_or_complete_main(
    changed_path: str, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        validation_gate,
        "changed_paths",
        lambda _base: [changed_path],
    )
    monkeypatch.setattr(
        validation_gate,
        "prepare_format_fastlane",
        lambda *_args, **_kwargs: 1,
    )
    monkeypatch.setattr(
        validation_gate,
        "_command",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("focused pytest must not start after a format failure")
        ),
    )
    monkeypatch.setattr(
        validation_gate.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("the complete main gate must not start")
        ),
    )

    result = validation_gate.run_stage(
        "commit",
        "base",
        tmp_path,
        True,
        fix_format=True,
    )

    assert result == 1


@pytest.mark.parametrize("stage", ["commit", "push"])
def test_no_cache_bypasses_reuse_without_changing_requested_tier(
    stage: str, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        validation_gate,
        "changed_paths",
        lambda _base: ["app/features/setup/service.py"],
    )
    monkeypatch.setattr(
        validation_gate,
        "candidate_fingerprint",
        lambda _base, requested_stage, _paths: f"{requested_stage}-key",
    )
    monkeypatch.setattr(
        validation_gate,
        "prepare_format_fastlane",
        lambda *_args, **_kwargs: 0,
    )
    labels = []
    monkeypatch.setattr(
        validation_gate,
        "_command",
        lambda label, _command, _env: labels.append(label) or 0,
    )
    monkeypatch.setattr(
        validation_gate.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("--no-cache must not dispatch the complete main gate")
        ),
    )

    result = validation_gate.run_stage(
        stage,
        "base",
        tmp_path,
        True,
        fix_format=False,
    )

    assert result == 0
    assert "affected tests" in labels
    assert ("quality baseline" in labels) is (stage == "push")


def test_pre_submit_no_cache_still_dispatches_the_tiered_gate() -> None:
    script = (
        Path(__file__).resolve().parents[2] / "scripts/pre_submit_gate.sh"
    ).read_text(encoding="utf-8")

    assert 'if [[ "$DIRECT_MAIN" -eq 0 ]]; then' in script
    assert 'if [[ "$NO_CACHE" -eq 0 && "$DIRECT_MAIN" -eq 0 ]]; then' not in script
    assert "VALIDATION_ARGS+=(--no-cache)" in script


def test_validation_gate_forwards_a_custom_cache_root_to_g1_and_g2(
    tmp_path: Path, monkeypatch
) -> None:
    captured = []
    monkeypatch.setenv("ELFIENEST_VALIDATION_CACHE_ROOT", str(tmp_path))
    monkeypatch.setattr(validation_gate, "changed_paths", lambda _base: [])
    monkeypatch.setattr(
        validation_gate,
        "run_stage",
        lambda stage, base, cache_root, no_cache, fix_format=False: (
            captured.append((stage, base, cache_root, no_cache, fix_format)) or 0
        ),
    )

    assert validation_gate.main(["--stage", "commit", "--base-sha", "base"]) == 0
    assert captured == [("commit", "base", tmp_path, False, False)]


def test_complete_gate_does_not_repeat_quality_baseline_through_pre_commit() -> None:
    root = Path(__file__).resolve().parents[2]
    script = (root / "scripts/pre_submit_gate.sh").read_text(encoding="utf-8")
    pre_commit = (root / ".pre-commit-config.yaml").read_text(encoding="utf-8")

    assert script.count("scripts/check_quality_baseline.py") == 1
    assert "-m pre_commit run gitleaks --all-files" in script
    assert "quality-baseline" not in pre_commit


def test_submit_skill_uses_git_only_for_remote_operations() -> None:
    skill = (
        Path(__file__).resolve().parents[2]
        / ".agents/skills/git-submit-and-push/SKILL.md"
    ).read_text(encoding="utf-8")

    assert "只使用终端 `git` 命令" in skill
    assert "调用 `gh`" in skill
    assert "github-cli-operations" not in skill


def test_main_gate_reuses_node_dependencies_when_manifests_are_unchanged() -> None:
    script = (
        Path(__file__).resolve().parents[2] / "scripts/pre_submit_gate.sh"
    ).read_text(encoding="utf-8")

    assert "node_modules/.modules.yaml" in script
    assert 'git -C "$PROJECT_ROOT" diff --quiet "$BASE_SHA"' in script
    assert "ensure_pnpm_dependencies" in script
    assert 'ln -s "$reusable_modules/.pnpm" "$directory/node_modules/.pnpm"' in script
    assert "Keep the candidate's node_modules root writable" in script


def test_main_gate_exposes_the_controlled_interpreter_inside_candidate_tree() -> None:
    script = (
        Path(__file__).resolve().parents[2] / "scripts/pre_submit_gate.sh"
    ).read_text(encoding="utf-8")

    assert 'ln -s "$PROJECT_ROOT/.venv" "$CANDIDATE_ROOT/.venv"' in script
