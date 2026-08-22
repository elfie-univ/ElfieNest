"""Machine gates for the repository architecture-governance system."""

from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Optional, Set

import scripts.architecture.check_governance_change as governance_change
from scripts.architecture.check_governance_change import (
    ConformanceRow,
    classify_paths,
    has_closure_ready_marker,
    has_complete_closure_evidence,
    parse_conformance_rows,
    validate_baseline_changes,
    validate_conformance_changes,
    validate_contract_changes,
    validate_decision_mirrors,
    validate_governance_rule_changes,
    validate_temporary_cleanup_changes,
)
from scripts.architecture.contract_registry import CONTRACT_REGISTRY

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _registered_paths(attribute: str) -> Set[str]:
    paths: Set[str] = set()
    for registration in CONTRACT_REGISTRY:
        paths.update(getattr(registration, attribute))
    return paths


def test_contract_registry_has_unique_ids_and_existing_artifacts() -> None:
    ids = [registration.contract_id for registration in CONTRACT_REGISTRY]
    assert len(ids) == len(set(ids))

    for registration in CONTRACT_REGISTRY:
        required_paths = {
            registration.english_path,
            registration.chinese_path,
            *registration.decision_paths,
            *registration.agent_paths,
            *registration.scanner_paths,
            *registration.test_paths,
            *registration.conformance_paths,
        }
        if registration.baseline_path is not None:
            required_paths.add(registration.baseline_path)
        missing = {
            path for path in required_paths if not (PROJECT_ROOT / path).is_file()
        }
        assert missing == set(), f"{registration.contract_id}: {sorted(missing)}"


def test_registered_contract_versions_match_bilingual_mirrors() -> None:
    for registration in CONTRACT_REGISTRY:
        english = (PROJECT_ROOT / registration.english_path).read_text(encoding="utf-8")
        chinese = (PROJECT_ROOT / registration.chinese_path).read_text(encoding="utf-8")
        assert f"**Contract version:** {registration.version}" in english
        assert f"**契约版本：** {registration.version}" in chinese


def test_every_architecture_test_is_owned_by_a_registered_contract() -> None:
    actual = {
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in (PROJECT_ROOT / "test" / "architecture").glob("test_*.py")
    }
    assert actual == _registered_paths("test_paths")


def _conformance_rows(relative_path: str) -> dict[str, ConformanceRow]:
    source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
    return parse_conformance_rows(source)


def test_registered_temporary_debt_artifacts_are_live() -> None:
    for registration in CONTRACT_REGISTRY:
        for relative_path in registration.conformance_paths:
            source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
            rows = _conformance_rows(relative_path)
            assert rows, f"no conformance rows: {relative_path}"
            if all(row.status == "closed" for row in rows.values()):
                assert has_closure_ready_marker(source), (
                    f"all-closed conformance must be marked ready: {relative_path}"
                )
                assert all(
                    has_complete_closure_evidence(row) for row in rows.values()
                ), f"closure-ready conformance needs row evidence: {relative_path}"

        if registration.baseline_path is None:
            continue
        namespace = runpy.run_path(str(PROJECT_ROOT / registration.baseline_path))
        baselines = [
            value
            for name, value in namespace.items()
            if name.startswith("LEGACY_") and isinstance(value, dict)
        ]
        assert baselines, f"no legacy baseline mapping: {registration.baseline_path}"
        assert any(
            entries for baseline in baselines for entries in baseline.values()
        ), (
            f"empty baseline must be removed from the registry: "
            f"{registration.baseline_path}"
        )


def test_retired_task_closure_paths_are_governance_changes() -> None:
    governance, production = classify_paths(
        {
            "scripts/check_task_closure.py",
            "task-closure.json",
            "task-closure-lifecycle.json",
            "task-closure-model-availability.json",
            "task-closure-telegram.json",
            "task-closure-third-batch.json",
            "test/scripts/test_check_task_closure.py",
        }
    )

    assert production == set()
    assert governance == {
        "scripts/check_task_closure.py",
        "task-closure.json",
        "task-closure-lifecycle.json",
        "task-closure-model-availability.json",
        "task-closure-telegram.json",
        "task-closure-third-batch.json",
        "test/scripts/test_check_task_closure.py",
    }


def test_contract_change_requires_mirror_version_bump_and_bilingual_adr(
    tmp_path: Path,
    monkeypatch,
) -> None:
    english_contract = "docs/developer/contracts/example.md"
    chinese_contract = "docs/zh/developer/contracts/example.md"
    english_decision = "docs/developer/decisions/0001-example.md"
    chinese_decision = "docs/zh/developer/decisions/0001-example.md"
    for path, source in (
        (english_contract, "**Contract version:** 2.0\n"),
        (chinese_contract, "**契约版本：** 2.0\n"),
        (english_decision, "decision\n"),
        (chinese_decision, "决策\n"),
    ):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    def base_source(_base_sha: str, path: str) -> str:
        if path == english_contract:
            return "**Contract version:** 1.0\n"
        if path == chinese_contract:
            return "**契约版本：** 1.0\n"
        raise AssertionError(path)

    monkeypatch.setattr(governance_change, "_base_source", base_source)
    changed = {
        english_contract,
        chinese_contract,
        english_decision,
        chinese_decision,
    }
    assert validate_contract_changes("base", changed) == []
    assert validate_decision_mirrors(changed) == []

    missing_mirrors = {english_contract, english_decision}
    failures = [
        *validate_contract_changes("base", missing_mirrors),
        *validate_decision_mirrors(missing_mirrors),
    ]
    assert any("contract mirror not changed" in failure for failure in failures)
    assert any("ADR mirror not changed" in failure for failure in failures)

    (tmp_path / english_contract).write_text(
        "**Contract version:** 1.0\n", encoding="utf-8"
    )
    (tmp_path / chinese_contract).write_text("**契约版本：** 1.0\n", encoding="utf-8")
    failures = validate_contract_changes("base", changed)
    assert (
        len(
            [
                failure
                for failure in failures
                if "contract version not bumped" in failure
            ]
        )
        == 2
    )


def test_contract_indexes_require_mirrors_but_not_contract_versions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    english_index = "docs/developer/contracts/index.md"
    chinese_index = "docs/zh/developer/contracts/index.md"
    english_decision = "docs/developer/decisions/0001-example.md"
    chinese_decision = "docs/zh/developer/decisions/0001-example.md"
    for path in (
        english_index,
        chinese_index,
        english_decision,
        chinese_decision,
    ):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("index or decision\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        governance_change,
        "_base_source",
        lambda _base_sha, _path: "previous index or decision\n",
    )
    changed = {
        english_index,
        chinese_index,
        english_decision,
        chinese_decision,
    }

    assert validate_contract_changes("base", changed) == []
    assert validate_decision_mirrors(changed) == []


def test_changed_path_inventory_includes_deletions(monkeypatch) -> None:
    captured: list[str] = []

    def fake_run(command, **_kwargs):
        captured.extend(command)
        return SimpleNamespace(stdout="docs/developer/conformance/example.md\n")

    monkeypatch.setattr(governance_change.subprocess, "run", fake_run)

    assert governance_change.changed_paths("base") == [
        "docs/developer/conformance/example.md"
    ]
    assert "--diff-filter=ACDMRTUXB" in captured


def test_governance_checker_supports_the_documented_direct_cli() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/architecture/check_governance_change.py",
            "--help",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "--base-sha" in result.stdout
    assert "--paths" in result.stdout


def test_governance_checker_accepts_explicit_candidate_paths(monkeypatch) -> None:
    monkeypatch.setattr(
        governance_change,
        "changed_paths",
        lambda _base: (_ for _ in ()).throw(
            AssertionError("explicit paths must bypass the committed diff")
        ),
    )
    monkeypatch.setattr(
        governance_change,
        "validate_baseline_changes",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        governance_change,
        "validate_contract_changes",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        governance_change,
        "validate_decision_mirrors",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        governance_change,
        "validate_governance_rule_changes",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        governance_change,
        "validate_conformance_changes",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        governance_change,
        "validate_temporary_cleanup_changes",
        lambda *_args, **_kwargs: [],
    )

    assert (
        governance_change.main(
            ["--base-sha", "base", "--paths", "docs/developer/guide.md"]
        )
        == 0
    )


def test_newly_closed_conformance_requires_inventory_and_reference_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    english = "docs/developer/conformance/example.md"
    chinese = "docs/zh/developer/conformance/example.md"
    registry = "scripts/architecture/contract_registry.py"
    registry_source = f'conformance_paths=("{english}", "{chinese}")\n'
    for path, source in (
        (
            english,
            "| ID | Severity | Status | Deviation | Gate | Evidence |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| EX-001 | P0 | closed | fixed | met | tests passed |\n",
        ),
        (
            chinese,
            "| ID | 严重度 | 状态 | 偏差 | 条件 | 证据 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| EX-001 | P0 | closed | 已修复 | 已满足 | 测试通过 |\n",
        ),
        (registry, registry_source),
    ):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    base_english = (
        "| ID | Severity | Status | Deviation | Gate | Evidence |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| EX-001 | P0 | open | gap | gate | pending |\n"
    )
    base_chinese = (
        "| ID | 严重度 | 状态 | 偏差 | 条件 | 证据 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| EX-001 | P0 | open | 缺口 | 条件 | pending |\n"
    )

    def base_source(_base_sha: str, path: str) -> Optional[str]:
        return {
            english: base_english,
            chinese: base_chinese,
            registry: registry_source,
        }.get(path)

    monkeypatch.setattr(governance_change, "_base_source", base_source)
    changed = {english, chinese}
    failures = validate_conformance_changes(
        "base", changed, governance=set(), production={"nest/example.py"}
    )
    assert any("lacks complete cleanup evidence" in item for item in failures)
    assert any("not marked ready" in item for item in failures)

    evidence = (
        "target=contract-1; inventory=scope-list; references=callers-scan; "
        "verification=positive-and-negative; residuals=zero"
    )
    (tmp_path / english).write_text(
        "**Closure state:** ready\n"
        "| ID | Severity | Status | Deviation | Gate | Evidence |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        f"| EX-001 | P0 | closed | fixed | met | {evidence} |\n",
        encoding="utf-8",
    )
    (tmp_path / chinese).write_text(
        "**收口状态：** ready\n"
        "| ID | 严重度 | 状态 | 偏差 | 条件 | 证据 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        f"| EX-001 | P0 | closed | 已修复 | 已满足 | {evidence} |\n",
        encoding="utf-8",
    )
    assert (
        validate_conformance_changes(
            "base", changed, governance=set(), production={"nest/example.py"}
        )
        == []
    )


def test_conformance_removal_is_checked_against_the_base_register(
    tmp_path: Path,
    monkeypatch,
) -> None:
    english = "docs/developer/conformance/example.md"
    chinese = "docs/zh/developer/conformance/example.md"
    registry = "scripts/architecture/contract_registry.py"
    base_registry = f'conformance_paths=("{english}", "{chinese}")\n'
    candidate_registry = tmp_path / registry
    candidate_registry.parent.mkdir(parents=True)
    candidate_registry.write_text("conformance_paths=()\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    documents = {
        english: "| EX-001 | P0 | open | gap | gate | pending |\n",
        chinese: "| EX-001 | P0 | open | 缺口 | 条件 | pending |\n",
    }

    def base_source(_base_sha: str, path: str) -> Optional[str]:
        if path == registry:
            return base_registry
        return documents.get(path)

    monkeypatch.setattr(governance_change, "_base_source", base_source)
    changed = {registry, english, chinese}
    failures = validate_conformance_changes(
        "base", changed, governance={registry}, production=set()
    )
    assert any("open base rows" in item for item in failures)

    evidence = (
        "target=contract-1; inventory=scope-list; references=callers-scan; "
        "verification=positive-and-negative; residuals=zero"
    )
    documents[english] = (
        "**Closure state:** ready\n"
        f"| EX-001 | P0 | closed | fixed | met | {evidence} |\n"
    )
    documents[chinese] = (
        "**收口状态：** ready\n"
        f"| EX-001 | P0 | closed | 已修复 | 已满足 | {evidence} |\n"
    )
    assert (
        validate_conformance_changes(
            "base", changed, governance={registry}, production=set()
        )
        == []
    )
    failures = validate_conformance_changes(
        "base", changed, governance={registry}, production={"nest/example.py"}
    )
    assert any("governance-only" in item for item in failures)


def test_closed_conformance_evidence_cannot_be_weakened(
    tmp_path: Path,
    monkeypatch,
) -> None:
    english = "docs/developer/conformance/example.md"
    chinese = "docs/zh/developer/conformance/example.md"
    registry = "scripts/architecture/contract_registry.py"
    registry_source = f'conformance_paths=("{english}", "{chinese}")\n'
    complete = (
        "target=contract-1; inventory=scope-list; references=callers-scan; "
        "verification=positive-and-negative; residuals=zero"
    )
    candidate_sources = {
        english: "| EX-001 | P0 | closed | fixed | met | pending |\n",
        chinese: "| EX-001 | P0 | closed | 已修复 | 已满足 | pending |\n",
        registry: registry_source,
    }
    for path, source in candidate_sources.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    def base_source(_base_sha: str, path: str) -> Optional[str]:
        if path == registry:
            return registry_source
        if path == english:
            return f"| EX-001 | P0 | closed | fixed | met | {complete} |\n"
        if path == chinese:
            return f"| EX-001 | P0 | closed | 已修复 | 已满足 | {complete} |\n"
        return None

    monkeypatch.setattr(governance_change, "_base_source", base_source)
    failures = validate_conformance_changes(
        "base", {english, chinese}, governance=set(), production={"nest/example.py"}
    )
    assert any("evidence may not regress" in item for item in failures)


def test_open_conformance_row_cannot_disappear_from_a_live_register(
    tmp_path: Path,
    monkeypatch,
) -> None:
    english = "docs/developer/conformance/example.md"
    chinese = "docs/zh/developer/conformance/example.md"
    registry = "scripts/architecture/contract_registry.py"
    registry_source = f'conformance_paths=("{english}", "{chinese}")\n'
    for path, source in (
        (english, "| EX-002 | P0 | open | gap | gate | pending |\n"),
        (chinese, "| EX-002 | P0 | open | 缺口 | 条件 | pending |\n"),
        (registry, registry_source),
    ):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    def base_source(_base_sha: str, path: str) -> Optional[str]:
        if path == registry:
            return registry_source
        if path == english:
            return "| EX-001 | P0 | open | old | gate | pending |\n"
        if path == chinese:
            return "| EX-001 | P0 | open | 旧项 | 条件 | pending |\n"
        return None

    monkeypatch.setattr(governance_change, "_base_source", base_source)
    failures = validate_conformance_changes(
        "base", {english, chinese}, governance=set(), production={"nest/example.py"}
    )
    assert any("may close but not disappear" in item for item in failures)


def test_closed_cleanup_paths_are_no_longer_registered_as_temporary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    relative_path = "nest/state/new_compatibility.py"
    candidate = tmp_path / relative_path
    candidate.parent.mkdir(parents=True)
    candidate.write_text("legacy = True\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        governance_change, "_base_source", lambda _base_sha, _path: None
    )

    failures = validate_temporary_cleanup_changes("base", {relative_path})
    assert failures == []

    monkeypatch.setattr(
        governance_change, "_base_source", lambda _base_sha, _path: "old\n"
    )
    assert validate_temporary_cleanup_changes("base", {relative_path}) == []

    candidate.unlink()
    assert validate_temporary_cleanup_changes("base", {relative_path}) == []


def test_frozen_macro_contract_requires_a_new_standalone_bilingual_adr(
    tmp_path: Path,
    monkeypatch,
) -> None:
    english_contract = "docs/developer/contracts/system.md"
    chinese_contract = "docs/zh/developer/contracts/system.md"
    old_english_adr = "docs/developer/decisions/0002-system-ports-adapters.md"
    old_chinese_adr = "docs/zh/developer/decisions/0002-system-ports-adapters.md"
    new_english_adr = "docs/developer/decisions/0004-macro-change.md"
    new_chinese_adr = "docs/zh/developer/decisions/0004-macro-change.md"
    for path, source in (
        (english_contract, "**Contract version:** 2.0\n"),
        (chinese_contract, "**契约版本：** 2.0\n"),
        (old_english_adr, "updated old decision\n"),
        (old_chinese_adr, "更新旧决策\n"),
        (new_english_adr, "new decision\n"),
        (new_chinese_adr, "新决策\n"),
    ):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    def base_source(_base_sha: str, path: str) -> Optional[str]:
        if path == english_contract:
            return "**Contract version:** 1.0\n"
        if path == chinese_contract:
            return "**契约版本：** 1.0\n"
        if path in {old_english_adr, old_chinese_adr}:
            return "old decision\n"
        if path in {new_english_adr, new_chinese_adr}:
            return None
        raise AssertionError(path)

    monkeypatch.setattr(governance_change, "_base_source", base_source)
    old_adr_change = {
        english_contract,
        chinese_contract,
        old_english_adr,
        old_chinese_adr,
    }
    failures = validate_contract_changes("base", old_adr_change)
    assert any("without a new standalone bilingual ADR" in item for item in failures)

    new_adr_change = {
        english_contract,
        chinese_contract,
        new_english_adr,
        new_chinese_adr,
    }
    assert validate_contract_changes("base", new_adr_change) == []


def test_quality_gate_definitions_are_governance_but_baseline_can_shrink() -> None:
    governance, production = classify_paths(
        {
            ".pre-commit-config.yaml",
            ".quality-baseline.json",
            "scripts/check_quality_baseline.py",
            "app/features/setup/service.py",
        }
    )
    assert governance == {
        ".pre-commit-config.yaml",
        "scripts/check_quality_baseline.py",
    }
    assert production == {
        ".quality-baseline.json",
        "app/features/setup/service.py",
    }


def test_repository_wide_implementation_surfaces_cannot_hide_in_governance_change() -> (
    None
):
    governance, production = classify_paths(
        {
            "docs/developer/contracts/repository-governance.md",
            "devtools/nest_lab/__main__.py",
            "scripts/release.py",
            "developer.sh",
            "pyproject.toml",
            "test/app/test_product_flow.py",
            "docs/.vitepress/config.mts",
            "docs/package.json",
            ".github/workflows/docs.yml",
            "new_surface/entry.custom",
        }
    )

    assert governance == {
        "docs/developer/contracts/repository-governance.md",
    }
    assert production == {
        ".github/workflows/docs.yml",
        "developer.sh",
        "devtools/nest_lab/__main__.py",
        "docs/.vitepress/config.mts",
        "docs/package.json",
        "new_surface/entry.custom",
        "pyproject.toml",
        "scripts/release.py",
        "test/app/test_product_flow.py",
    }


def test_governance_artifacts_take_precedence_over_implementation_roots() -> None:
    governance, production = classify_paths(
        {
            ".github/workflows/ci.yml",
            "scripts/architecture/effective_dependency_scan.py",
            "scripts/check_quality_baseline.py",
            "test/architecture/test_effective_dependency_boundaries.py",
            "test/architecture/baselines/app_layer.py",
            "test/architecture/baselines/__init__.py",
        }
    )

    assert governance == {
        ".github/workflows/ci.yml",
        "scripts/architecture/effective_dependency_scan.py",
        "scripts/check_quality_baseline.py",
        "test/architecture/baselines/__init__.py",
        "test/architecture/test_effective_dependency_boundaries.py",
    }
    assert production == {"test/architecture/baselines/app_layer.py"}


def test_ordinary_documentation_remains_neutral_for_change_classification() -> None:
    governance, production = classify_paths(
        {
            "README.md",
            "LICENSE",
            "docs/user-guide/configuration.md",
            "docs/zh/user-guide/configuration.md",
            "scripts/README.md",
        }
    )

    assert governance == set()
    assert production == set()


def test_architecture_baseline_may_only_shrink_from_the_base_commit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    baseline_path = "test/architecture/baselines/app_layer.py"
    contract_path = "docs/developer/contracts/repository-governance.md"
    base_source = 'LEGACY_APP_LAYER_VIOLATIONS = {"rule": frozenset({"old", "keep"})}\n'
    candidate = tmp_path / baseline_path
    candidate.parent.mkdir(parents=True)
    candidate.write_text(
        'LEGACY_APP_LAYER_VIOLATIONS = {"rule": frozenset({"keep"})}\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    def base_file(_base_sha: str, path: str) -> str:
        if path == contract_path:
            return "contract"
        if path == baseline_path:
            return base_source
        raise AssertionError(path)

    monkeypatch.setattr(governance_change, "_base_source", base_file)
    assert validate_baseline_changes("base", {baseline_path}, governance=set()) == []

    candidate.write_text(
        'LEGACY_APP_LAYER_VIOLATIONS = {"rule": frozenset({"new"})}\n',
        encoding="utf-8",
    )
    failures = validate_baseline_changes("base", {baseline_path}, governance=set())
    assert any("entries added or rewritten" in failure for failure in failures)

    candidate.write_text(
        'LEGACY_APP_LAYER_VIOLATIONS = {"rule": frozenset({"keep"})}\n',
        encoding="utf-8",
    )
    failures = validate_baseline_changes(
        "base", {baseline_path, "AGENTS.md"}, governance={"AGENTS.md"}
    )
    assert "governance changes may not edit legacy architecture baselines" in failures

    candidate.unlink()
    failures = validate_baseline_changes(
        "base", {baseline_path, "AGENTS.md"}, governance={"AGENTS.md"}
    )
    assert any("may only delete an empty" in failure for failure in failures)

    empty_base_source = 'LEGACY_APP_LAYER_VIOLATIONS = {"rule": frozenset({})}\n'

    def empty_base_file(_base_sha: str, path: str) -> str:
        if path == contract_path:
            return "contract"
        if path == baseline_path:
            return empty_base_source
        raise AssertionError(path)

    monkeypatch.setattr(governance_change, "_base_source", empty_base_file)
    assert (
        validate_baseline_changes(
            "base", {baseline_path, "AGENTS.md"}, governance={"AGENTS.md"}
        )
        == []
    )


def test_new_baseline_is_allowed_only_for_the_initial_governance_bootstrap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    baseline_path = "test/architecture/baselines/system_layer.py"
    candidate = tmp_path / baseline_path
    candidate.parent.mkdir(parents=True)
    candidate.write_text("LEGACY_SYSTEM_LAYER_VIOLATIONS = {}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    def established_base(_base_sha: str, path: str) -> Optional[str]:
        if path == "docs/developer/contracts/repository-governance.md":
            return "contract"
        return None

    monkeypatch.setattr(governance_change, "_base_source", established_base)
    failures = validate_baseline_changes("base", {baseline_path}, governance=set())
    assert failures == [f"new architecture baseline is forbidden: {baseline_path}"]

    monkeypatch.setattr(
        governance_change, "_base_source", lambda _base_sha, _path: None
    )
    assert validate_baseline_changes("base", {baseline_path}, governance=set()) == []


def test_baseline_package_marker_is_governance_not_a_legacy_baseline() -> None:
    marker = "test/architecture/baselines/__init__.py"

    assert governance_change.is_governance_file(marker)
    assert validate_baseline_changes("base", {marker}, governance={marker}) == []


def test_executable_governance_rule_change_requires_bilingual_adr_update() -> None:
    failures = validate_governance_rule_changes(
        {"scripts/architecture/system_layer_scan.py"}
    )
    assert any("without a bilingual ADR update" in failure for failure in failures)

    assert (
        validate_governance_rule_changes(
            {
                "scripts/architecture/system_layer_scan.py",
                "docs/developer/decisions/0004-rule-change.md",
                "docs/zh/developer/decisions/0004-rule-change.md",
            }
        )
        == []
    )


def test_architecture_ratchet_uses_the_immutable_base_router() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    preflight = workflow.split("  security-fast:", maxsplit=1)[0]
    architecture_job = workflow.split("  architecture-governance:", maxsplit=1)[
        1
    ].split("  persistence-contract:", maxsplit=1)[0]

    assert "github.event.pull_request.base.sha" in preflight
    assert "$base_sha:scripts/architecture/validation_plan.py" in preflight
    assert "base branch predates the trusted router; selecting every lane" in preflight
    assert (
        "$BASE_SHA:scripts/architecture/check_governance_change.py" in architecture_job
    )
    assert "$BASE_SHA:scripts/architecture/structural_scope_scan.py" in architecture_job
    assert 'PYTHONPATH="$classifier_root"' in architecture_job


def test_ci_runs_complete_architecture_once_premerge_and_full_only_postsubmit() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    architecture_job = workflow.split("  architecture-governance:", maxsplit=1)[
        1
    ].split("  persistence-contract:", maxsplit=1)[0]
    postsubmit_job = workflow.split("  postsubmit-full:", maxsplit=1)[1]
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert architecture_job.count("pytest test/architecture/") == 1
    assert "--stage full --direct-full" in postsubmit_job
    assert "uv run --no-sync pytest --cov" not in workflow
    assert 'testpaths = ["test"]' in pyproject
