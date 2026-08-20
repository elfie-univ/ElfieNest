#!/usr/bin/env python3
"""Plan and run the repository's tiered, reusable validation workflow."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.architecture.validation_cache import (
    backstop_fingerprint,
    cache_hit,
    cache_lock,
    cache_store,
    candidate_fingerprint,
)
from scripts.architecture.validation_plan import TIER_NAMES, build_plan, changed_paths


def _command(label: str, command: Sequence[str], env: Dict[str, str]) -> int:
    print(f"\n==> {label}: {' '.join(command)}")
    return subprocess.run(
        list(command), cwd=PROJECT_ROOT, env=env, check=False
    ).returncode


def _git_path_list(arguments: Sequence[str]) -> List[str]:
    result = subprocess.run(
        ["git", *arguments],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def _format_fix_scope(
    candidate_paths: Sequence[str],
    staged_paths: Sequence[str],
    unstaged_paths: Sequence[str],
    untracked_paths: Sequence[str],
) -> Tuple[List[str], List[str]]:
    """Return Python paths that may be formatted and unsafe mixed-index paths."""

    candidates = set(candidate_paths)
    staged = set(staged_paths)
    unstaged = set(unstaged_paths)
    untracked = set(untracked_paths)

    def is_python(path: str) -> bool:
        return path.endswith((".py", ".pyi"))

    mixed_set = {path for path in candidates & staged & unstaged if is_python(path)}
    mixed = sorted(mixed_set)
    fixable = sorted(
        path
        for path in candidates & (unstaged | untracked)
        if path not in mixed_set and is_python(path) and (PROJECT_ROOT / path).is_file()
    )
    return fixable, mixed


def prepare_format_fastlane(
    base_sha: str,
    paths: Sequence[str],
    *,
    fix_format: bool,
    env: Dict[str, str],
) -> int:
    """Run deterministic formatting checks before any test or broad backstop."""

    staged = _git_path_list(("diff", "--cached", "--name-only", "--"))
    unstaged = _git_path_list(("diff", "--name-only", "--"))
    untracked = _git_path_list(("ls-files", "--others", "--exclude-standard"))
    fixable, mixed = _format_fix_scope(paths, staged, unstaged, untracked)

    if fix_format and mixed:
        print(
            "❌ refusing automatic formatting for paths with both staged and "
            f"unstaged content: {', '.join(mixed)}",
            file=sys.stderr,
        )
        return 1

    uv = shutil.which("uv") or "uv"
    if fix_format and fixable:
        if (
            _command(
                "formatting changed Python files",
                [uv, "run", "--no-sync", "ruff", "format", *fixable],
                env,
            )
            != 0
        ):
            return 1

    if _command("diff format", ["git", "diff", "--check", base_sha, "--"], env) != 0:
        return 1

    python_paths = sorted(
        path
        for path in set(paths)
        if path.endswith((".py", ".pyi")) and (PROJECT_ROOT / path).is_file()
    )
    if not python_paths:
        return 0
    if (
        _command(
            "focused Ruff format",
            [uv, "run", "--no-sync", "ruff", "format", "--check", *python_paths],
            env,
        )
        != 0
    ):
        return 1
    return _command(
        "focused Ruff check",
        [uv, "run", "--no-sync", "ruff", "check", *python_paths],
        env,
    )


def _commands(
    plan: Dict[str, object],
    base_sha: str,
    *,
    no_cache: bool = False,
) -> List[Tuple[str, List[str]]]:
    uv = shutil.which("uv") or "uv"
    commands: List[Tuple[str, List[str]]] = []
    plan_tests = cast(Sequence[object], plan["tests"])
    tests = [path for path in plan_tests if isinstance(path, str)]
    if tests:
        affected_command = [
            sys.executable,
            "scripts/architecture/validation_test_bundles.py",
            "--base-sha",
            base_sha,
            "--selectors",
            *tests,
        ]
        if no_cache:
            affected_command.append("--no-cache")
        commands.append(("affected tests", affected_command))
    if int(cast(int, plan["effective_tier"])) >= 2:
        commands.append(
            (
                "quality baseline",
                [uv, "run", "--no-sync", "python", "scripts/check_quality_baseline.py"],
            )
        )
        if plan["architecture"]:
            commands.append(
                (
                    "architecture tests",
                    [uv, "run", "--no-sync", "pytest", "test/architecture/"],
                )
            )
        if plan["docs_site"]:
            commands.append(
                (
                    "documentation build",
                    ["pnpm", "--dir", "docs", "install", "--frozen-lockfile"],
                )
            )
            commands.append(("documentation build", ["pnpm", "--dir", "docs", "build"]))
    return commands


def _main_revalidation_commands(
    paths: Sequence[str],
) -> List[Tuple[str, List[str]]]:
    """Checks that remain candidate-specific after a G3 backstop is reused."""

    uv = shutil.which("uv") or "uv"
    commands: List[Tuple[str, List[str]]] = []
    gitleaks_paths = [path for path in paths if (PROJECT_ROOT / path).is_file()]
    if gitleaks_paths:
        commands.append(
            (
                "changed-file secret scan",
                [
                    uv,
                    "run",
                    "--no-sync",
                    "pre-commit",
                    "run",
                    "gitleaks",
                    "--files",
                    *gitleaks_paths,
                ],
            )
        )
    return commands


def run_stage(
    stage: str,
    base_sha: str,
    cache_root: Path,
    no_cache: bool,
    fix_format: bool = False,
) -> int:
    paths = changed_paths(base_sha)
    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", "/tmp/elfienest-uv-cache")
    env.setdefault("PRE_COMMIT_HOME", "/tmp/elfienest-precommit")
    if (
        prepare_format_fastlane(
            base_sha,
            paths,
            fix_format=fix_format,
            env=env,
        )
        != 0
    ):
        return 1
    paths = changed_paths(base_sha)
    plan = build_plan(paths, stage)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if stage == "main" or int(cast(int, plan["effective_tier"])) == 3:
        key = candidate_fingerprint(base_sha, "main", paths)
        backstop_key = backstop_fingerprint(base_sha, paths)
        lock = cache_root / f"{backstop_key}.lock"
        with cache_lock(lock):
            current_paths = changed_paths(base_sha)
            current_key = candidate_fingerprint(base_sha, "main", current_paths)
            if current_key != key:
                print(
                    "❌ worktree changed before main validation; rerun the fast lane",
                    file=sys.stderr,
                )
                return 1
            if not no_cache and cache_hit(cache_root, key):
                print(f"✅ reused exact passed main gate: {key}")
                return 0
            if not no_cache and cache_hit(cache_root, backstop_key):
                print(
                    "✅ reusing passed expensive main backstop; "
                    "rechecking current candidate metadata"
                )
                for label, command in _main_revalidation_commands(
                    paths,
                ):
                    if _command(label, command, env) != 0:
                        return 1
                after = candidate_fingerprint(base_sha, "main", changed_paths(base_sha))
                if after != key:
                    print(
                        "❌ worktree changed during metadata revalidation; "
                        "result was discarded",
                        file=sys.stderr,
                    )
                    return 1
                cache_store(
                    cache_root,
                    key,
                    "main",
                    base_sha,
                    reused_from=backstop_key,
                )
                print(
                    "✅ main validation passed without repeating full pytest, "
                    "dependency installs, or documentation build"
                )
                return 0
            main_command = [
                "bash",
                "scripts/pre_submit_gate.sh",
                "--stage",
                "main",
                "--direct-main",
                "--base-sha",
                base_sha,
            ]
            if no_cache:
                main_command.append("--no-cache")
            main_env = os.environ.copy()
            main_env["ELFIENEST_VALIDATION_CACHE_ROOT"] = str(cache_root)
            result = subprocess.run(
                main_command,
                cwd=PROJECT_ROOT,
                env=main_env,
                check=False,
            ).returncode
            after = candidate_fingerprint(base_sha, "main", changed_paths(base_sha))
            if result == 0 and after != key:
                print(
                    "❌ worktree changed during main validation; result was discarded",
                    file=sys.stderr,
                )
                return 1
            if result == 0 and not no_cache:
                cache_store(cache_root, backstop_key, "main-backstop", base_sha)
                cache_store(cache_root, key, "main", base_sha)
            return result
    key = candidate_fingerprint(base_sha, stage, paths)
    lock = cache_root / f"{key}.lock"
    with cache_lock(lock):
        current_paths = changed_paths(base_sha)
        current_key = candidate_fingerprint(base_sha, stage, current_paths)
        if current_key != key:
            print(
                f"❌ worktree changed before {stage} validation; rerun the fast lane",
                file=sys.stderr,
            )
            return 1
        if not no_cache and cache_hit(cache_root, key):
            print(f"✅ reused exact passed {stage} validation: {key}")
            return 0
        before = key
        gitleaks_paths = [path for path in paths if (PROJECT_ROOT / path).is_file()]
        commands = _commands(plan, base_sha, no_cache=no_cache)
        if gitleaks_paths:
            commands.insert(
                1,
                (
                    "changed-file secret scan",
                    [
                        shutil.which("uv") or "uv",
                        "run",
                        "--no-sync",
                        "pre-commit",
                        "run",
                        "gitleaks",
                        "--files",
                        *gitleaks_paths,
                    ],
                ),
            )
        for label, command in commands:
            if _command(label, command, env) != 0:
                return 1
        if candidate_fingerprint(base_sha, stage, changed_paths(base_sha)) != before:
            print(
                "❌ worktree changed during validation; result was not cached",
                file=sys.stderr,
            )
            return 1
        if not no_cache:
            cache_store(cache_root, key, stage, base_sha)
        print(f"✅ {stage} validation passed")
        return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=tuple(TIER_NAMES.values()), required=True)
    parser.add_argument("--base-sha", default="")
    parser.add_argument(
        "--cache-root",
        default=os.environ.get(
            "ELFIENEST_VALIDATION_CACHE_ROOT", "build/validation-cache"
        ),
    )
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--fix-format", action="store_true")
    args = parser.parse_args(argv)
    base = (
        args.base_sha
        or subprocess.check_output(
            ["git", "rev-parse", "origin/main^{commit}"], cwd=PROJECT_ROOT, text=True
        ).strip()
    )
    plan = build_plan(changed_paths(base), args.stage)
    if args.plan_only:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    return run_stage(
        args.stage,
        base,
        PROJECT_ROOT / args.cache_root,
        args.no_cache,
        args.fix_format,
    )


if __name__ == "__main__":
    raise SystemExit(main())
