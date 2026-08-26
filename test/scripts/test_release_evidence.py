from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.internal.release.release_evidence import (
    ReleaseEvidenceError,
    aggregate_release_evidence,
)

TARGETS = ("darwin-arm64", "darwin-x64", "win32-x64", "linux-x64")
CANDIDATE = "a" * 40


def _write_fixture(root: Path, target: str, *, source_commit: str = CANDIDATE) -> Path:
    artifact = root / f"ElfieNest-{target}.pkg"
    artifact.write_bytes(f"artifact:{target}".encode())
    evidence = root / f"{target}.json"
    evidence.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "target": target,
                "artifact": artifact.name,
                "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                "source_commit": source_commit,
                "runner": {"RUNNER_OS": "test"},
                "cycles": [{"product_journey": {"result": "passed"}}],
                "result": "passed",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return evidence


def test_aggregate_binds_all_targets_to_candidate_and_package_hashes(
    tmp_path: Path,
) -> None:
    evidence = [_write_fixture(tmp_path, target) for target in TARGETS]
    output = tmp_path / "aggregate.json"

    result = aggregate_release_evidence(
        evidence,
        artifact_dir=tmp_path,
        candidate_sha=CANDIDATE,
        output=output,
    )

    assert result["result"] == "passed"
    assert set(result["targets"]) == set(TARGETS)
    assert json.loads(output.read_text(encoding="utf-8"))["candidate_sha"] == CANDIDATE


def test_aggregate_rejects_source_mismatch_and_secret_bearing_summary(
    tmp_path: Path,
) -> None:
    evidence = [_write_fixture(tmp_path, target) for target in TARGETS]
    mismatch = tmp_path / "darwin-arm64.json"
    payload = json.loads(mismatch.read_text(encoding="utf-8"))
    payload["source_commit"] = "b" * 40
    mismatch.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ReleaseEvidenceError, match="source-mismatch"):
        aggregate_release_evidence(
            evidence,
            artifact_dir=tmp_path,
            candidate_sha=CANDIDATE,
            output=tmp_path / "aggregate.json",
        )

    payload["source_commit"] = CANDIDATE
    payload["secret"] = "session_token"
    mismatch.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ReleaseEvidenceError, match="secret-sentinel"):
        aggregate_release_evidence(
            evidence,
            artifact_dir=tmp_path,
            candidate_sha=CANDIDATE,
            output=tmp_path / "aggregate.json",
        )


def test_aggregate_requires_product_journey_by_default(tmp_path: Path) -> None:
    evidence = [_write_fixture(tmp_path, target) for target in TARGETS]
    payload = json.loads(evidence[0].read_text(encoding="utf-8"))
    payload["cycles"] = [{}]
    evidence[0].write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ReleaseEvidenceError, match="journey-missing"):
        aggregate_release_evidence(
            evidence,
            artifact_dir=tmp_path,
            candidate_sha=CANDIDATE,
            output=tmp_path / "aggregate.json",
        )
