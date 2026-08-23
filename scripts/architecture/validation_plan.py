#!/usr/bin/env python3
"""Build the trusted changed-path manifest used by local and GitHub validation."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

PROJECT_ROOT = Path(
    os.environ.get("ELFIENEST_PROJECT_ROOT", Path(__file__).resolve().parents[2])
).resolve()

MANIFEST_SCHEMA_VERSION = "affected-v2"
TIER_NAMES = {1: "commit", 2: "push", 3: "full"}
STAGE_TIERS = {"commit": 1, "push": 2, "full": 3, "main": 3}
CAPABILITY_NAMES = (
    "security_fast",
    "python_bundles",
    "python_quality",
    "web_frontend",
    "desktop",
    "devtools_web",
    "architecture",
    "persistence_contract",
    "godot",
    "docs",
    "toolchain",
    "release",
    "runtime_smoke",
    "governance",
)

GOVERNANCE_PREFIXES = (
    ".agents/skills/",
    ".github/",
    "docs/developer/contracts/",
    "docs/developer/decisions/",
    "docs/zh/developer/contracts/",
    "docs/zh/developer/decisions/",
    "scripts/architecture/",
    "task-closure",
    "test/architecture/",
)
GOVERNANCE_EXACT = frozenset(
    {
        "AGENTS.md",
        ".gitignore",
        ".pre-commit-config.yaml",
        ".quality-baseline.json",
        "CONTRIBUTING.md",
        "CONTRIBUTING_zh.md",
        "scripts/check_quality_baseline.py",
        "scripts/pre_submit_gate.sh",
    }
)
TOOLCHAIN_EXACT = frozenset(
    {
        ".python-version",
        "package.json",
        "pnpm-lock.yaml",
        "pyproject.toml",
        "scripts/check_node_toolchain.sh",
        "uv.lock",
    }
)
TOOLCHAIN_PREFIXES = ("scripts/bootstrap",)
RELEASE_PREFIXES = (
    ".github/workflows/release",
    "app/bootstrap/desktop_host/",
    "scripts/build_",
    "scripts/package_",
    "scripts/release",
)
PROVIDER_PREFIXES = (
    "app/features/configuration/providers/",
    "app/features/configuration/food/",
    "app/interfaces/api/v1/admin/model_providers/",
    "infrastructure/models/providers/",
    "infrastructure/models/validation/provider",
    "infrastructure/models/provider_",
    "infrastructure/persistence/provider",
)
PROVIDER_EXACT = frozenset(
    {
        "infrastructure/models/catalog.py",
        "infrastructure/models/capabilities.py",
        "infrastructure/models/model_reference.py",
        "infrastructure/models/setup_catalog.py",
        "infrastructure/models/setup_provider.py",
        "infrastructure/persistence/model_catalog.py",
        "infrastructure/persistence/model_health_projection.py",
        "infrastructure/persistence/validation_artifacts.py",
        "infrastructure/persistence/reports/validation_reports.py",
    }
)
PROVIDER_TESTS = (
    "test/infrastructure/models/validation/test_provider_validation.py",
    "test/infrastructure/models/validation/test_provider_validation_behaviors.py",
    "test/infrastructure/models/validation/test_provider_model_matrix.py",
    "test/infrastructure/models/validation/test_provider_capability_probes.py",
    "test/infrastructure/models/validation/test_provider_scheduler.py",
    "test/infrastructure/models/test_provider_administration.py",
    "test/infrastructure/models/test_provider_catalog.py",
    "test/infrastructure/models/test_provider_http.py",
    "test/infrastructure/models/test_provider_model_hints.py",
    "test/infrastructure/models/test_provider_profiles.py",
    "test/infrastructure/models/test_setup_provider.py",
    "test/infrastructure/models/providers/test_dispatch_options.py",
    "test/infrastructure/models/providers/test_request_profiles.py",
    "test/infrastructure/persistence/test_provider_availability.py",
    "test/infrastructure/persistence/test_provider_connection_mutations.py",
    "test/infrastructure/persistence/test_provider_connections.py",
    "test/infrastructure/persistence/reports/test_validation_reports.py",
    "test/app/features/configuration/providers/test_service.py",
    "test/app/features/configuration/food/test_policy.py",
    "test/app/features/configuration/food/test_service.py",
    "test/app/interfaces/api/v1/admin/model_providers/test_routes.py",
    "test/app/interfaces/api/v1/admin/model_providers/test_model_batch_routes.py",
)
PYTHON_BUNDLE_BY_ROOT = {
    "app/": "test/app",
    "elfie/": "test/elfie",
    "infrastructure/": "test/infrastructure",
    "nest/": "test/nest",
    "scripts/": "test/scripts",
}
FULL_PYTHON_BUNDLES = (
    "test/app",
    "test/devtools",
    "test/e2e",
    "test/elfie",
    "test/infrastructure",
    "test/nest",
    "test/scripts",
)
GENERATED_GATE_OUTPUTS = frozenset({"coverage.xml"})
NEUTRAL_SUFFIXES = (".md", ".rst", ".txt")


def _run_lines(command: Sequence[str]) -> List[str]:
    result = subprocess.run(
        list(command), cwd=PROJECT_ROOT, check=True, capture_output=True, text=True
    )
    return [line for line in result.stdout.splitlines() if line]


def changed_paths(base_sha: str) -> List[str]:
    tracked = _run_lines(
        [
            "git",
            "diff",
            "--name-only",
            "--no-renames",
            "--diff-filter=ACDMRTUXB",
            base_sha,
            "--",
        ]
    )
    untracked = _run_lines(["git", "ls-files", "--others", "--exclude-standard"])
    return sorted(set(tracked + untracked) - GENERATED_GATE_OUTPUTS)


def _test_path_for_source(path: str) -> Optional[str]:
    if not path.endswith(".py") or Path(path).parent == Path("."):
        return None
    candidate = PROJECT_ROOT / "test" / path
    if candidate.is_file():
        return candidate.relative_to(PROJECT_ROOT).as_posix()
    directory = PROJECT_ROOT / "test" / Path(path).parent
    if directory.is_dir():
        return directory.relative_to(PROJECT_ROOT).as_posix()
    return None


def _python_bundle(path: str) -> Optional[str]:
    for prefix, bundle in PYTHON_BUNDLE_BY_ROOT.items():
        if path.startswith(prefix):
            return bundle
    return None


def _is_toolchain_path(path: str) -> bool:
    return (
        path in TOOLCHAIN_EXACT
        or path.startswith(TOOLCHAIN_PREFIXES)
        or path.endswith(("package.json", "pnpm-lock.yaml"))
    )


def build_plan(paths: Iterable[str], requested_stage: str) -> Dict[str, object]:
    if requested_stage not in STAGE_TIERS:
        raise ValueError(f"unknown validation stage: {requested_stage}")

    normalized_stage = "full" if requested_stage == "main" else requested_stage
    normalized_paths = sorted(set(paths))
    selected: set[str] = set()
    selected_capabilities: set[str] = {"security_fast"}
    reasons: List[str] = []
    unknown_paths: List[str] = []
    full = normalized_stage == "full"
    required_tier = 1

    for path in normalized_paths:
        if path in GENERATED_GATE_OUTPUTS:
            continue
        if (
            Path(path).name == "AGENTS.md"
            or path.startswith(GOVERNANCE_PREFIXES)
            or path in GOVERNANCE_EXACT
        ):
            selected_capabilities.update({"architecture", "governance"})
            if path.startswith(("docs/", "docs/zh/")):
                selected_capabilities.add("docs")
            required_tier = max(required_tier, 2)
            full = True
            reasons.append(f"{path} changes validation or repository governance")
            continue
        if _is_toolchain_path(path):
            selected_capabilities.add("toolchain")
            required_tier = max(required_tier, 2)
            full = True
            reasons.append(f"{path} changes a pinned toolchain or dependency manifest")
            if path.startswith("docs/"):
                selected_capabilities.add("docs")
            if path.startswith("app/interfaces/web/frontend/"):
                selected_capabilities.add("web_frontend")
            if path.startswith("app/interfaces/desktop/"):
                selected_capabilities.add("desktop")
            if path.startswith("devtools/web/"):
                selected_capabilities.add("devtools_web")
            continue
        if path.startswith(RELEASE_PREFIXES):
            selected_capabilities.add("release")
            required_tier = max(required_tier, 2)
            full = True
            reasons.append(f"{path} changes packaging or release behavior")
            continue
        if path.startswith("app/interfaces/web/frontend/"):
            selected_capabilities.add("web_frontend")
            reasons.append(f"{path} is owned by the web frontend lane")
            continue
        if path.startswith("app/interfaces/desktop/"):
            selected_capabilities.add("desktop")
            reasons.append(f"{path} is owned by the desktop lane")
            continue
        if path.startswith("devtools/web/"):
            selected_capabilities.add("devtools_web")
            reasons.append(f"{path} is owned by the Developer Tools web lane")
            continue
        if path.startswith("docs/"):
            selected_capabilities.add("docs")
            reasons.append(f"{path} is consumed by the documentation lane")
            continue
        if path.startswith(("godot_project/", "test/godot/")):
            selected_capabilities.add("godot")
            reasons.append(f"{path} is owned by the Godot lane")
            continue
        if path.startswith(
            ("infrastructure/persistence/", "test/infrastructure/persistence/")
        ):
            selected_capabilities.add("persistence_contract")
        if path.startswith(("infrastructure/godot/", "test/infrastructure/godot/")):
            selected_capabilities.add("godot")
        if path.startswith(PROVIDER_PREFIXES) or path in PROVIDER_EXACT:
            selected.update(PROVIDER_TESTS)
            selected_capabilities.update(
                {"python_bundles", "python_quality", "persistence_contract"}
            )
            required_tier = max(required_tier, 2)
            reasons.append(f"{path} is in the Provider/model configuration flow")
            continue
        if path.startswith("test/") and path.endswith(".py"):
            selected.add(path)
            selected_capabilities.update({"python_bundles", "python_quality"})
            reasons.append(f"{path} directly selects its Python test")
            continue
        bundle = _python_bundle(path)
        if bundle is not None:
            selected_capabilities.update({"python_bundles", "python_quality"})
            test_path = _test_path_for_source(path)
            selected.add(test_path or bundle)
            reasons.append(f"{path} selects the affected {bundle} tests")
            continue
        if path.startswith(("config/", "resources/")):
            selected_capabilities.update(
                {"python_bundles", "python_quality", "persistence_contract"}
            )
            selected.update(("test/app", "test/infrastructure", "test/scripts"))
            required_tier = max(required_tier, 2)
            reasons.append(f"{path} changes shared runtime configuration")
            continue
        if path.endswith(NEUTRAL_SUFFIXES):
            reasons.append(f"{path} is non-executable documentation")
            continue

        unknown_paths.append(path)
        full = True
        required_tier = max(required_tier, 2)
        reasons.append(f"{path} is an unknown executable path and fails closed")

    direct_capabilities = set(selected_capabilities)
    direct_tests = {path for path in selected if (PROJECT_ROOT / path).exists()}
    if full:
        selected_capabilities = set(CAPABILITY_NAMES)
        selected.update(FULL_PYTHON_BUNDLES)
    selected = {path for path in selected if (PROJECT_ROOT / path).exists()}
    requested_tier = STAGE_TIERS[requested_stage]
    effective_tier = max(required_tier, requested_tier)
    if not reasons:
        reasons.append("no executable changes require affected validation")
    capabilities = {name: name in selected_capabilities for name in CAPABILITY_NAMES}
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "requested_stage": normalized_stage,
        "requested_tier": requested_tier,
        "effective_tier": effective_tier,
        "effective_stage": TIER_NAMES[effective_tier],
        "full": full,
        "paths": normalized_paths,
        "tests": sorted(selected),
        "direct_tests": sorted(direct_tests),
        "unknown_paths": unknown_paths,
        "capabilities": capabilities,
        "direct_capabilities": {
            name: name in direct_capabilities for name in CAPABILITY_NAMES
        },
        "architecture": capabilities["architecture"],
        "docs_site": capabilities["docs"],
        "reasons": reasons,
    }


def _write_github_outputs(path: Path, plan: Dict[str, object]) -> None:
    capabilities = plan["capabilities"]
    assert isinstance(capabilities, dict)
    outputs = {
        "router_version": plan["schema_version"],
        "manifest_json": json.dumps(plan, ensure_ascii=False, separators=(",", ":")),
        "tests_json": json.dumps(
            plan["tests"], ensure_ascii=False, separators=(",", ":")
        ),
        "unknown_paths_json": json.dumps(
            plan["unknown_paths"], ensure_ascii=False, separators=(",", ":")
        ),
        "full": str(bool(plan["full"])).lower(),
        **{name: str(bool(capabilities[name])).lower() for name in CAPABILITY_NAMES},
    }
    with path.open("a", encoding="utf-8") as output:
        for name, value in outputs.items():
            output.write(f"{name}={value}\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-sha", default="")
    parser.add_argument("--stage", choices=tuple(STAGE_TIERS), default="push")
    parser.add_argument("--paths", nargs="*")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)
    paths = args.paths if args.paths is not None else changed_paths(args.base_sha)
    plan = build_plan(paths, args.stage)
    if args.github_output is not None:
        _write_github_outputs(args.github_output, plan)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
