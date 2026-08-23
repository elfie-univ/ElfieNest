#!/usr/bin/env python3
"""Build the immutable identity for reusable pre-PR candidate evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Callable, Dict, Optional, Sequence

PROJECT_ROOT = Path(
    os.environ.get("ELFIENEST_PROJECT_ROOT", Path(__file__).resolve().parents[3])
).resolve()
EVIDENCE_SCHEMA_VERSION = "candidate-evidence-v1"
WORKFLOW_IDENTITY = "CI:.github/workflows/ci.yml@refs/heads/main"
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
MANIFEST_PATTERN = re.compile(r'MANIFEST_SCHEMA_VERSION = "([^"]+)"')

GOVERNANCE_FINGERPRINT_PATHS = (
    ".github/workflows/ci.yml",
    ".pre-commit-config.yaml",
    "AGENTS.md",
    "docs/developer/contracts/repository-governance.md",
    "docs/zh/developer/contracts/repository-governance.md",
    "scripts/governance/change_policy.py",
    "scripts/governance/contract_registry.py",
    "scripts/pre_submit_gate.sh",
    "scripts/quality/hooks/install.sh",
    "scripts/quality/hooks/pre-commit",
    "scripts/quality/validation/cache.py",
    "scripts/quality/validation/candidate_evidence.py",
    "scripts/quality/validation/gate.py",
    "scripts/quality/validation/plan.py",
    "scripts/quality/validation/test_bundles.py",
)
TOOLCHAIN_FINGERPRINT_PATHS = (
    ".python-version",
    "pyproject.toml",
    "uv.lock",
    "package.json",
    "pnpm-lock.yaml",
    "app/interfaces/desktop/package.json",
    "app/interfaces/desktop/pnpm-lock.yaml",
    "app/interfaces/web/frontend/package.json",
    "app/interfaces/web/frontend/pnpm-lock.yaml",
    "devtools/web/package.json",
    "devtools/web/pnpm-lock.yaml",
    "docs/package.json",
    "docs/pnpm-lock.yaml",
)


def _validate_sha(value: str, label: str) -> None:
    if not SHA_PATTERN.fullmatch(value):
        raise ValueError(f"{label} must be an exact 40-character lowercase SHA")


def _git_blob(commit_sha: str, path: str, project_root: Path = PROJECT_ROOT) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit_sha}:{path}"],
        cwd=project_root,
        check=False,
        capture_output=True,
    )
    if result.returncode == 0:
        return result.stdout
    return b"<missing>"


def _fingerprint(
    commit_sha: str,
    paths: Sequence[str],
    reader: Callable[[str, str], bytes],
) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.encode("utf-8") + b"\0")
        digest.update(reader(commit_sha, path) + b"\0")
    return digest.hexdigest()


def build_identity(
    base_sha: str,
    candidate_sha: str,
    *,
    reader: Optional[Callable[[str, str], bytes]] = None,
) -> Dict[str, str]:
    """Return every identity component required for safe evidence reuse."""

    _validate_sha(base_sha, "base SHA")
    _validate_sha(candidate_sha, "candidate SHA")
    read_blob = reader or (lambda commit, path: _git_blob(commit, path))
    governance_fingerprint = _fingerprint(
        base_sha, GOVERNANCE_FINGERPRINT_PATHS, read_blob
    )
    toolchain_fingerprint = _fingerprint(
        candidate_sha, TOOLCHAIN_FINGERPRINT_PATHS, read_blob
    )
    plan_source = read_blob(base_sha, "scripts/quality/validation/plan.py").decode(
        "utf-8", errors="replace"
    )
    manifest_match = MANIFEST_PATTERN.search(plan_source)
    if manifest_match is None:
        raise ValueError("base validation plan has no recognized manifest version")
    manifest_version = manifest_match.group(1)
    artifact_name = "--".join(
        (
            EVIDENCE_SCHEMA_VERSION,
            candidate_sha,
            governance_fingerprint,
            manifest_version,
            toolchain_fingerprint,
        )
    )
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "candidate_sha": candidate_sha,
        "base_governance_fingerprint": governance_fingerprint,
        "manifest_version": manifest_version,
        "candidate_toolchain_fingerprint": toolchain_fingerprint,
        "workflow_identity": WORKFLOW_IDENTITY,
        "artifact_name": artifact_name,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--format", choices=("json", "name"), default="json")
    args = parser.parse_args(argv)
    identity = build_identity(args.base_sha, args.candidate_sha)
    if args.format == "name":
        print(identity["artifact_name"])
    else:
        print(json.dumps(identity, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
