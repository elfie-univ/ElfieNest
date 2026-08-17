"""Changed-path impact classification for the tiered validation gate."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TIER_NAMES = {1: "commit", 2: "push", 3: "main"}
HIGH_RISK_PREFIXES = (
    ".agents/skills/",
    ".github/",
    "docs/developer/contracts/",
    "docs/developer/decisions/",
    "docs/zh/developer/contracts/",
    "docs/zh/developer/decisions/",
    "scripts/architecture/",
    "test/architecture/",
)
HIGH_RISK_EXACT = frozenset(
    {
        "AGENTS.md",
        ".pre-commit-config.yaml",
        "CONTRIBUTING.md",
        "CONTRIBUTING_zh.md",
        "pyproject.toml",
        "uv.lock",
        "package.json",
        "pnpm-lock.yaml",
        "scripts/check_task_closure.py",
        "scripts/pre_submit_gate.sh",
        "task-closure.json",
        "task-closure-lifecycle.json",
        "task-closure-model-availability.json",
        "task-closure-telegram.json",
        "task-closure-third-batch.json",
        "test/scripts/test_check_task_closure.py",
    }
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
PYTHON_ROOTS = ("app/", "elfie/", "infrastructure/", "nest/", "scripts/")
GENERATED_GATE_OUTPUTS = frozenset({"coverage.xml"})


def _run_lines(command: Sequence[str]) -> List[str]:
    result = subprocess.run(
        list(command), cwd=PROJECT_ROOT, check=True, capture_output=True, text=True
    )
    return [line for line in result.stdout.splitlines() if line]


def changed_paths(base_sha: str) -> List[str]:
    tracked = _run_lines(["git", "diff", "--name-only", base_sha, "--"])
    untracked = _run_lines(["git", "ls-files", "--others", "--exclude-standard"])
    return sorted(set(tracked + untracked) - GENERATED_GATE_OUTPUTS)


def _test_path_for_source(path: str) -> Optional[str]:
    if not path.endswith(".py"):
        return None
    if Path(path).parent == Path("."):
        return None
    candidate = PROJECT_ROOT / "test" / path
    if candidate.is_file():
        return candidate.relative_to(PROJECT_ROOT).as_posix()
    directory = PROJECT_ROOT / "test" / Path(path).parent
    if directory.is_dir():
        return directory.relative_to(PROJECT_ROOT).as_posix()
    return None


def build_plan(paths: Iterable[str], requested_stage: str) -> Dict[str, object]:
    selected: set[str] = set()
    reasons: List[str] = []
    required_tier = 1
    architecture = False
    docs_site = False
    for path in sorted(set(paths)):
        if path.startswith(HIGH_RISK_PREFIXES) or path in HIGH_RISK_EXACT:
            required_tier = 3
            reasons.append(f"{path} changes validation or delivery governance")
            architecture = architecture or path.startswith("scripts/architecture/")
            continue
        if path.endswith(("package.json", "pnpm-lock.yaml")):
            required_tier = 3
            docs_site = docs_site or path.startswith("docs/")
            reasons.append(f"{path} changes a toolchain manifest or lockfile")
        elif path.startswith("docs/.vitepress/"):
            required_tier = max(required_tier, 2)
            docs_site = docs_site or path.startswith("docs/")
            reasons.append(f"{path} has a direct documentation build consumer")
        elif path.startswith(PROVIDER_PREFIXES) or path in PROVIDER_EXACT:
            required_tier = max(required_tier, 2)
            selected.update(PROVIDER_TESTS)
            reasons.append(f"{path} is in the Provider/model configuration flow")
        elif path.startswith("test/") and path.endswith(".py"):
            selected.add(path)
        elif path.endswith(".md") or path.endswith(".rst"):
            reasons.append(f"{path} is non-executable documentation")
        else:
            test_path = _test_path_for_source(path)
            if test_path is None and any(
                path.startswith(root) for root in PYTHON_ROOTS
            ):
                required_tier = 3
                reasons.append(f"{path} has no deterministic focused-test mapping")
            elif test_path:
                selected.add(test_path)
            else:
                required_tier = 3
                reasons.append(f"{path} is an unknown executable path")
    selected = {path for path in selected if (PROJECT_ROOT / path).exists()}
    requested_tier = {"commit": 1, "push": 2, "main": 3}[requested_stage]
    effective_tier = max(required_tier, requested_tier)
    if not reasons:
        reasons.append("no executable changes require escalation")
    return {
        "requested_stage": requested_stage,
        "requested_tier": requested_tier,
        "effective_tier": effective_tier,
        "effective_stage": TIER_NAMES[effective_tier],
        "paths": sorted(set(paths)),
        "tests": sorted(selected),
        "architecture": architecture,
        "docs_site": docs_site,
        "reasons": reasons,
    }
