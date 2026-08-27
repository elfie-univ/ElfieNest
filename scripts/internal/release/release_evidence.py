#!/usr/bin/env python3
"""Validate and aggregate exact-target native release evidence.

The aggregator is intentionally independent from the native smoke runner.  It
binds each redacted summary to one candidate commit and one package checksum,
rejects duplicate/missing targets and never copies raw logs or credentials into
the aggregate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

SUPPORTED_TARGETS = {
    "darwin-arm64",
    "darwin-x64",
    "win32-x64",
    "linux-x64",
}
EVIDENCE_SCHEMA_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_COMMIT = re.compile(r"^[0-9a-fA-F]{40}$")
_FORBIDDEN_SENTINELS = (
    "Authorization",
    "session_token",
    "setup_token",
    "elfienest-release-synthetic-credential",
    "ElfieNest-Release-2026!",
)


class ReleaseEvidenceError(ValueError):
    """Raised when a target summary cannot be trusted for publication."""


def aggregate_release_evidence(
    evidence_paths: Sequence[Path],
    *,
    artifact_dir: Path,
    candidate_sha: str,
    output: Path,
    require_product_journey: bool = True,
) -> dict[str, Any]:
    """Validate four target summaries and write a redacted aggregate."""
    _require_commit(candidate_sha)
    if len(evidence_paths) != len(SUPPORTED_TARGETS):
        raise ReleaseEvidenceError("release-evidence-target-count-invalid")
    aggregate_targets: dict[str, dict[str, Any]] = {}
    for evidence_path in evidence_paths:
        payload = _load_object(evidence_path)
        target = payload.get("target")
        if not isinstance(target, str) or target not in SUPPORTED_TARGETS:
            raise ReleaseEvidenceError("release-evidence-target-invalid")
        if target in aggregate_targets:
            raise ReleaseEvidenceError("release-evidence-target-duplicate")
        if payload.get("result") != "passed":
            raise ReleaseEvidenceError(
                f"release-evidence-target-failed target={target}"
            )
        source_commit = payload.get("source_commit")
        if source_commit != candidate_sha:
            raise ReleaseEvidenceError(
                f"release-evidence-source-mismatch target={target}"
            )
        artifact_name = payload.get("artifact")
        artifact_sha = payload.get("artifact_sha256")
        if not isinstance(artifact_name, str) or not isinstance(artifact_sha, str):
            raise ReleaseEvidenceError(
                f"release-evidence-artifact-fields-missing target={target}"
            )
        _require_sha256(artifact_sha)
        artifact_path = (artifact_dir / artifact_name).resolve()
        if (
            artifact_path.parent != artifact_dir.resolve()
            or not artifact_path.is_file()
        ):
            raise ReleaseEvidenceError(
                f"release-evidence-artifact-missing target={target}"
            )
        actual_sha = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if actual_sha != artifact_sha.lower():
            raise ReleaseEvidenceError(
                f"release-evidence-artifact-mismatch target={target}"
            )
        cycles = payload.get("cycles")
        if not isinstance(cycles, list) or not cycles:
            raise ReleaseEvidenceError(
                f"release-evidence-cycles-missing target={target}"
            )
        if require_product_journey:
            for cycle in cycles:
                journey = (
                    cycle.get("product_journey") if isinstance(cycle, dict) else None
                )
                if not isinstance(journey, dict) or journey.get("result") != "passed":
                    raise ReleaseEvidenceError(
                        f"release-evidence-journey-missing target={target}"
                    )
        _assert_redacted(payload)
        aggregate_targets[target] = {
            "artifact": artifact_name,
            "artifact_sha256": artifact_sha.lower(),
            "evidence_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
            "cycles": len(cycles),
            "runner": _safe_runner(payload.get("runner")),
        }
    if set(aggregate_targets) != SUPPORTED_TARGETS:
        missing = sorted(SUPPORTED_TARGETS - set(aggregate_targets))
        raise ReleaseEvidenceError(
            "release-evidence-target-missing targets=" + ",".join(missing)
        )
    result = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "candidate_sha": candidate_sha.lower(),
        "targets": {
            target: aggregate_targets[target] for target in sorted(aggregate_targets)
        },
        "result": "passed",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def _load_object(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (
        FileNotFoundError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        raise ReleaseEvidenceError("release-evidence-json-invalid") from error
    if not isinstance(payload, dict):
        raise ReleaseEvidenceError("release-evidence-root-invalid")
    return payload


def _require_commit(value: str) -> None:
    if not _COMMIT.fullmatch(value):
        raise ReleaseEvidenceError("release-evidence-candidate-sha-invalid")


def _require_sha256(value: str) -> None:
    if not _SHA256.fullmatch(value):
        raise ReleaseEvidenceError("release-evidence-artifact-sha-invalid")


def _assert_redacted(payload: Mapping[str, Any]) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if any(sentinel in serialized for sentinel in _FORBIDDEN_SENTINELS):
        raise ReleaseEvidenceError("release-evidence-secret-sentinel")


def _safe_runner(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): str(item)
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, str) and len(item) <= 128
    }


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-missing-product-journey", action="store_true")
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_args(arguments)
    try:
        aggregate_release_evidence(
            args.evidence,
            artifact_dir=args.artifact_dir,
            candidate_sha=args.candidate_sha,
            output=args.output,
            require_product_journey=not args.allow_missing_product_journey,
        )
    except ReleaseEvidenceError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f"release-evidence-passed output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "EVIDENCE_SCHEMA_VERSION",
    "ReleaseEvidenceError",
    "aggregate_release_evidence",
]
