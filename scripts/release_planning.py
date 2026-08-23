"""Plan release work across native build runners without inventing artifacts."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Final, Optional, Sequence

from scripts.internal.build.package_python_core import TARGETS

SUPPORTED_TARGETS: Final[tuple[str, ...]] = TARGETS


class ReleasePlanError(RuntimeError):
    """Raised when a requested release matrix is not well-defined."""


@dataclass(frozen=True)
class ReleaseRequest:
    """One immutable target request handed to exactly one native runner."""

    target: str
    version: str
    source_commit: str
    input_manifest: str


@dataclass(frozen=True)
class RunnerResult:
    """The evidence a runner must return before its target may be complete."""

    target: str
    status: str
    artifact: Optional[Path]
    artifact_size: Optional[int]
    artifact_sha256: Optional[str]
    smoke_evidence: Optional[str]
    error: Optional[str]


@dataclass(frozen=True)
class ReleaseSession:
    """Aggregate result for one complete requested target matrix."""

    requests: tuple[ReleaseRequest, ...]
    results: tuple[RunnerResult, ...]
    status: str


RunnerAdapter = Callable[[ReleaseRequest], RunnerResult]


@dataclass(frozen=True)
class ReleasePlan:
    """The local and remote work needed for one requested release matrix."""

    native_targets: tuple[str, ...]
    requires_native_runner: tuple[str, ...]

    @property
    def is_complete(self) -> bool:
        """Whether the current runner can execute every requested target."""
        return not self.requires_native_runner


def plan_release(requested_targets: Sequence[str], host_target: str) -> ReleasePlan:
    """Partition a complete, unique target request by the active native runner."""
    targets = tuple(requested_targets)
    if not targets:
        raise ReleasePlanError("release-targets-empty")
    unknown = tuple(target for target in targets if target not in SUPPORTED_TARGETS)
    if unknown:
        raise ReleasePlanError(
            f"release-target-unsupported targets={','.join(unknown)}"
        )
    if len(set(targets)) != len(targets):
        raise ReleasePlanError("release-targets-duplicated")
    if host_target not in SUPPORTED_TARGETS:
        raise ReleasePlanError(f"release-host-target-unsupported target={host_target}")
    native_targets = tuple(target for target in targets if target == host_target)
    remote_targets = tuple(target for target in targets if target != host_target)
    return ReleasePlan(
        native_targets=native_targets,
        requires_native_runner=remote_targets,
    )


def release_requests(
    targets: Sequence[str],
    version: str,
    source_commit: str,
    input_manifest: str,
) -> tuple[ReleaseRequest, ...]:
    """Build a validated, complete request set without selecting a runner."""
    _validate_targets(targets)
    if not version:
        raise ReleasePlanError("release-version-empty")
    if len(source_commit) != 40:
        raise ReleasePlanError("release-source-commit-invalid")
    if len(input_manifest) != 64:
        raise ReleasePlanError("release-input-manifest-invalid")
    return tuple(
        ReleaseRequest(
            target=target,
            version=version,
            source_commit=source_commit,
            input_manifest=input_manifest,
        )
        for target in targets
    )


def coordinate_release(
    requests: Sequence[ReleaseRequest],
    adapters: dict[str, RunnerAdapter],
) -> ReleaseSession:
    """Dispatch every target concurrently and retain evidence from completed peers."""
    if not requests:
        raise ReleasePlanError("release-requests-empty")
    _validate_targets(tuple(request.target for request in requests))
    results: dict[str, RunnerResult] = {}
    runnable = [request for request in requests if request.target in adapters]
    for request in requests:
        if request.target not in adapters:
            results[request.target] = RunnerResult(
                target=request.target,
                status="incomplete",
                artifact=None,
                artifact_size=None,
                artifact_sha256=None,
                smoke_evidence=None,
                error="release-runner-unavailable",
            )
    if runnable:
        with ThreadPoolExecutor(max_workers=len(runnable)) as executor:
            futures = {
                executor.submit(adapters[request.target], request): request
                for request in runnable
            }
            for future in as_completed(futures):
                request = futures[future]
                try:
                    result = future.result()
                    _validate_runner_result(request, result)
                except Exception as error:
                    result = RunnerResult(
                        target=request.target,
                        status="failed",
                        artifact=None,
                        artifact_size=None,
                        artifact_sha256=None,
                        smoke_evidence=None,
                        error=f"release-runner-failed cause={error}",
                    )
                results[request.target] = result
    ordered_results = tuple(results[request.target] for request in requests)
    return ReleaseSession(
        requests=tuple(requests),
        results=ordered_results,
        status=_session_status(ordered_results),
    )


def completed_runner_result(
    request: ReleaseRequest,
    artifact: Path,
    smoke_evidence: str,
) -> RunnerResult:
    """Produce a verified target result from a real installer and smoke record."""
    if not artifact.is_file():
        raise ReleasePlanError(f"release-artifact-missing target={request.target}")
    if not smoke_evidence:
        raise ReleasePlanError(
            f"release-smoke-evidence-missing target={request.target}"
        )
    payload = artifact.read_bytes()
    return RunnerResult(
        target=request.target,
        status="complete",
        artifact=artifact,
        artifact_size=len(payload),
        artifact_sha256=hashlib.sha256(payload).hexdigest(),
        smoke_evidence=smoke_evidence,
        error=None,
    )


def _validate_targets(targets: Sequence[str]) -> None:
    if not targets:
        raise ReleasePlanError("release-targets-empty")
    unknown = tuple(target for target in targets if target not in SUPPORTED_TARGETS)
    if unknown:
        raise ReleasePlanError(
            f"release-target-unsupported targets={','.join(unknown)}"
        )
    if len(set(targets)) != len(targets):
        raise ReleasePlanError("release-targets-duplicated")


def _validate_runner_result(request: ReleaseRequest, result: RunnerResult) -> None:
    if result.target != request.target:
        raise ReleasePlanError(
            f"release-runner-target-mismatch expected={request.target} actual={result.target}"
        )
    if result.status != "complete":
        return
    if (
        result.artifact is None
        or result.artifact_size is None
        or result.artifact_sha256 is None
        or not result.smoke_evidence
    ):
        raise ReleasePlanError(
            f"release-runner-evidence-incomplete target={request.target}"
        )
    if not result.artifact.is_file():
        raise ReleasePlanError(f"release-artifact-missing target={request.target}")
    payload = result.artifact.read_bytes()
    if (
        len(payload) != result.artifact_size
        or hashlib.sha256(payload).hexdigest() != result.artifact_sha256
    ):
        raise ReleasePlanError(
            f"release-artifact-checksum-mismatch target={request.target}"
        )


def _session_status(results: Sequence[RunnerResult]) -> str:
    if all(result.status == "complete" for result in results):
        return "complete"
    if any(result.status == "failed" for result in results):
        return "failed"
    return "incomplete"
