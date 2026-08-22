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


def _commands(
    plan: Dict[str, object],
    base_sha: str,
    *,
    no_cache: bool = False,
) -> List[Tuple[str, List[str]]]:
    uv = shutil.which("uv") or "uv"
    commands: List[Tuple[str, List[str]]] = [
        ("diff format", ["git", "diff", "--check", base_sha, "--"]),
    ]
    plan_paths = cast(Sequence[object], plan["paths"])
    candidate_paths = [path for path in plan_paths if isinstance(path, str)]
    paths = [
        path
        for path in candidate_paths
        if path.endswith(".py") and (PROJECT_ROOT / path).is_file()
    ]
    if paths:
        commands.extend(
            [
                (
                    "focused Ruff check",
                    [uv, "run", "--no-sync", "ruff", "check", *paths],
                ),
                (
                    "focused Ruff format",
                    [uv, "run", "--no-sync", "ruff", "format", "--check", *paths],
                ),
            ]
        )
    local_affected_only = bool(plan["full"]) and plan["requested_stage"] != "full"
    tests_key = "direct_tests" if local_affected_only else "tests"
    capabilities_key = "direct_capabilities" if local_affected_only else "capabilities"
    plan_tests = cast(Sequence[object], plan[tests_key])
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
        capabilities = cast(Dict[str, object], plan[capabilities_key])
        if capabilities["governance"]:
            commands.append(
                (
                    "governance change policy",
                    [
                        uv,
                        "run",
                        "--no-sync",
                        "python",
                        "scripts/architecture/check_governance_change.py",
                        "--base-sha",
                        base_sha,
                        "--paths",
                        *candidate_paths,
                    ],
                )
            )
        if capabilities["architecture"]:
            commands.append(
                (
                    "architecture tests",
                    [uv, "run", "--no-sync", "pytest", "test/architecture/"],
                )
            )
        if capabilities["persistence_contract"]:
            commands.append(
                (
                    "persistence contract",
                    [
                        uv,
                        "run",
                        "--no-sync",
                        "python",
                        "scripts/architecture/database_change_scan.py",
                        "--project-root",
                        ".",
                        "--base-sha",
                        base_sha,
                        "--check",
                    ],
                )
            )
        if capabilities["toolchain"]:
            commands.extend(
                [
                    ("dependency lock", [uv, "lock", "--check"]),
                    (
                        "Node toolchain manifests",
                        ["bash", "scripts/check_node_toolchain.sh"],
                    ),
                ]
            )
        if capabilities["docs"]:
            commands.append(
                (
                    "documentation build",
                    ["pnpm", "--dir", "docs", "install", "--frozen-lockfile"],
                )
            )
            commands.append(("documentation build", ["pnpm", "--dir", "docs", "build"]))
    capabilities = cast(Dict[str, object], plan[capabilities_key])
    if capabilities["web_frontend"]:
        frontend = "app/interfaces/web/frontend"
        commands.extend(
            [
                (
                    "web frontend dependencies",
                    ["pnpm", "--dir", frontend, "install", "--frozen-lockfile"],
                ),
                ("web frontend typecheck", ["pnpm", "--dir", frontend, "typecheck"]),
                ("web frontend tests", ["pnpm", "--dir", frontend, "test"]),
                ("web frontend build", ["pnpm", "--dir", frontend, "build"]),
            ]
        )
    if capabilities["desktop"]:
        desktop = "app/interfaces/desktop"
        commands.extend(
            [
                (
                    "desktop dependencies",
                    ["pnpm", "--dir", desktop, "install", "--frozen-lockfile"],
                ),
                ("desktop tests", ["pnpm", "--dir", desktop, "test"]),
            ]
        )
    if capabilities["devtools_web"]:
        devtools = "devtools/web"
        commands.extend(
            [
                (
                    "Developer Tools web dependencies",
                    ["pnpm", "--dir", devtools, "install", "--frozen-lockfile"],
                ),
                ("Developer Tools web tests", ["pnpm", "--dir", devtools, "test"]),
                ("Developer Tools web build", ["pnpm", "--dir", devtools, "build"]),
            ]
        )
    if capabilities["godot"]:
        godot_command = [
            sys.executable,
            "scripts/architecture/validation_test_bundles.py",
            "--base-sha",
            base_sha,
            "--selectors",
            "test/godot",
        ]
        if no_cache:
            godot_command.append("--no-cache")
        commands.append(("Godot contract tests", godot_command))
    if capabilities["release"]:
        commands.append(
            (
                "release metadata contract",
                [
                    uv,
                    "run",
                    "--no-sync",
                    "python",
                    "scripts/check_release_version.py",
                ],
            )
        )
    return commands


def _full_revalidation_commands(
    paths: Sequence[str],
    base_sha: str,
) -> List[Tuple[str, List[str]]]:
    """Checks that remain candidate-specific after a full backstop is reused."""

    uv = shutil.which("uv") or "uv"
    commands: List[Tuple[str, List[str]]] = [
        ("diff format", ["git", "diff", "--check", base_sha, "--"]),
    ]
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
) -> int:
    stage = "full" if stage == "main" else stage
    paths = changed_paths(base_sha)
    plan = build_plan(paths, stage)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if stage == "full":
        key = candidate_fingerprint(base_sha, "full", paths)
        backstop_key = backstop_fingerprint(base_sha, paths)
        lock = cache_root / f"{backstop_key}.lock"
        with cache_lock(lock):
            if not no_cache:
                current_paths = changed_paths(base_sha)
                current_key = candidate_fingerprint(base_sha, "full", current_paths)
                if current_key != key:
                    paths = current_paths
                    key = current_key
                    backstop_key = backstop_fingerprint(base_sha, paths)
            if not no_cache and cache_hit(cache_root, key):
                print(f"✅ reused exact passed full gate: {key}")
                return 0
            if not no_cache and cache_hit(cache_root, backstop_key):
                print(
                    "✅ reusing passed expensive full backstop; "
                    "rechecking current candidate metadata"
                )
                env = os.environ.copy()
                env.setdefault("UV_CACHE_DIR", "/tmp/elfienest-uv-cache")
                env.setdefault("PRE_COMMIT_HOME", "/tmp/elfienest-precommit")
                for label, command in _full_revalidation_commands(
                    paths,
                    base_sha,
                ):
                    if _command(label, command, env) != 0:
                        return 1
                after = candidate_fingerprint(base_sha, "full", changed_paths(base_sha))
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
                    "full",
                    base_sha,
                    reused_from=backstop_key,
                )
                print(
                    "✅ full validation passed without repeating pytest, "
                    "dependency installs, or documentation build"
                )
                return 0
            full_command = [
                "bash",
                "scripts/pre_submit_gate.sh",
                "--stage",
                "full",
                "--direct-full",
                "--base-sha",
                base_sha,
            ]
            if no_cache:
                full_command.append("--no-cache")
            full_env = os.environ.copy()
            full_env["ELFIENEST_VALIDATION_CACHE_ROOT"] = str(cache_root)
            result = subprocess.run(
                full_command,
                cwd=PROJECT_ROOT,
                env=full_env,
                check=False,
            ).returncode
            after = candidate_fingerprint(base_sha, "full", changed_paths(base_sha))
            if result == 0 and after != key:
                print(
                    "❌ worktree changed during full validation; result was discarded",
                    file=sys.stderr,
                )
                return 1
            if result == 0 and not no_cache:
                cache_store(cache_root, backstop_key, "full-backstop", base_sha)
                cache_store(cache_root, key, "full", base_sha)
            return result
    key = candidate_fingerprint(base_sha, stage, paths)
    lock = cache_root / f"{key}.lock"
    with cache_lock(lock):
        if not no_cache:
            current_paths = changed_paths(base_sha)
            current_key = candidate_fingerprint(base_sha, stage, current_paths)
            if current_key != key:
                paths = current_paths
                key = current_key
        if not no_cache and cache_hit(cache_root, key):
            print(f"✅ reused exact passed {stage} validation: {key}")
            return 0
        before = key
        env = os.environ.copy()
        env.setdefault("UV_CACHE_DIR", "/tmp/elfienest-uv-cache")
        env.setdefault("PRE_COMMIT_HOME", "/tmp/elfienest-precommit")
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
    parser.add_argument("--cache-root", default="build/validation-cache")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
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
    )


if __name__ == "__main__":
    raise SystemExit(main())
