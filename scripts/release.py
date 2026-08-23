#!/usr/bin/env python3
"""Coordinate strict native release builds without publishing artifacts."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Final, Optional, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.internal.build import package_python_core
from scripts.internal.release.release_install_smoke import (
    run_install_smoke as execute_install_smoke,
)
from scripts.internal.release.release_planning import (
    ReleasePlanError,
    ReleaseRequest,
    RunnerResult,
    completed_runner_result,
    coordinate_release,
    plan_release,
    release_requests,
)

SUPPORTED_TARGETS: Final[tuple[str, ...]] = package_python_core.TARGETS
PROJECT_ROOT: Final = Path(__file__).resolve().parents[1]


def parse_args(arguments: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse a release matrix; omission means the complete supported matrix."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        action="append",
        choices=SUPPORTED_TARGETS,
        help="a target for this release; repeat to request more than one",
    )
    parser.add_argument(
        "--artifact-output",
        type=Path,
        help="write the one complete locally built artifact path",
    )
    parser.add_argument(
        "--native-package-output",
        type=Path,
        help="write one current-host native package path before post-install smoke",
    )
    parser.add_argument(
        "--prebuilt-godot-web",
        action="store_true",
        help="reuse and validate a Godot Web Runtime built by an upstream release job",
    )
    parser.add_argument(
        "--run-install-smoke",
        action="store_true",
        help="run the native install/upgrade/start/stop/uninstall gate",
    )
    parser.add_argument(
        "--smoke-evidence-output",
        type=Path,
        help="write the typed native install smoke evidence JSON",
    )
    parser.add_argument(
        "--smoke-cycles",
        type=int,
        default=1,
        help="number of install/start/stop/upgrade smoke cycles",
    )
    return parser.parse_args(arguments)


def main(arguments: Optional[Sequence[str]] = None) -> int:
    """Coordinate one complete release matrix without uploading any artifacts."""
    args = parse_args(arguments)
    if args.artifact_output is not None and args.native_package_output is not None:
        print("release-artifact-output-options-conflict")
        return 2
    targets = tuple(args.target) if args.target else SUPPORTED_TARGETS
    try:
        plan = plan_release(targets, package_python_core.host_target())
    except (ReleasePlanError, package_python_core.NativeTargetRequiredError) as error:
        print(str(error))
        return 2
    if plan.native_targets and not uses_project_python():
        expected = project_python_path()
        print(f"release-python-required path={expected}")
        return 2
    if plan.native_targets and not ensure_release_environment():
        return 1
    if plan.native_targets:
        try:
            from scripts.internal.release import release_pipeline
        except ImportError as error:
            print(f"release-dependency-missing module={error.name}")
            return 1

    try:
        requests = release_requests(
            targets,
            version=release_version(),
            source_commit=source_commit(),
            input_manifest=release_input_manifest(),
        )
        adapters = {}
        if plan.native_targets:
            if args.prebuilt_godot_web:
                steps = release_pipeline.default_release_steps(prebuilt_godot_web=True)
            else:
                steps = release_pipeline.default_release_steps()
            adapters[package_python_core.host_target()] = _local_runner_adapter(
                release_pipeline,
                steps,
                run_install_smoke=args.run_install_smoke,
                smoke_evidence_output=args.smoke_evidence_output,
                smoke_cycles=args.smoke_cycles,
            )
        session = coordinate_release(requests, adapters)
    except (
        ReleasePlanError,
        release_pipeline.ReleasePipelineError,
        release_pipeline.NativeReleaseTargetError,
    ) as error:
        print(str(error))
        return 1
    artifacts = [
        result.artifact for result in session.results if result.artifact is not None
    ]
    for result in session.results:
        if result.artifact is not None:
            print(
                "release-target-built "
                f"target={result.target} artifact={result.artifact} "
                f"sha256={result.artifact_sha256 or 'unverified'}"
            )
        if result.status != "complete":
            print(
                f"release-target-{result.status} target={result.target} "
                f"reason={result.error or 'release-evidence-incomplete'}"
            )
    if args.artifact_output is not None:
        if len(artifacts) != 1 or session.status != "complete":
            print("release-artifact-output-requires-one-complete-native-target")
            return 2
        args.artifact_output.write_text(f"{artifacts[0].resolve()}\n", encoding="utf-8")
    if args.native_package_output is not None:
        if (
            len(artifacts) != 1
            or len(targets) != 1
            or targets[0] != package_python_core.host_target()
        ):
            print("release-native-package-output-requires-one-current-native-target")
            return 2
        args.native_package_output.write_text(
            f"{artifacts[0].resolve()}\n", encoding="utf-8"
        )
    return 0 if session.status == "complete" else 3


def _local_runner_adapter(
    release_pipeline_module,
    steps,
    *,
    run_install_smoke: bool = False,
    smoke_evidence_output: Optional[Path] = None,
    smoke_cycles: int = 1,
):
    """Return the current-host native builder and optional real install gate."""
    host_target = package_python_core.host_target()

    def run(request: ReleaseRequest) -> RunnerResult:
        artifact = release_pipeline_module.run_native_release(
            target=request.target,
            host_target=host_target,
            steps=steps,
        )
        payload = artifact.read_bytes()
        if run_install_smoke:
            evidence = smoke_evidence_output or (
                PROJECT_ROOT / "build" / "release-smoke" / f"{request.target}.json"
            )
            execute_install_smoke(
                request.target,
                artifact,
                evidence,
                cycles=smoke_cycles,
            )
            return completed_runner_result(
                request,
                artifact,
                str(evidence),
            )
        return RunnerResult(
            target=request.target,
            status="incomplete",
            artifact=artifact,
            artifact_size=len(payload),
            artifact_sha256=hashlib.sha256(payload).hexdigest(),
            smoke_evidence=None,
            error="release-install-smoke-unavailable",
        )

    return run


def release_version() -> str:
    """Read the checked release version without importing packaging-only code."""
    from scripts import check_release_version

    return check_release_version.project_version()


def source_commit() -> str:
    """Record the exact checkout commit used as a release input."""
    result = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    commit = result.stdout.strip()
    if result.returncode != 0 or len(commit) != 40:
        raise ReleasePlanError("release-source-commit-unavailable")
    return commit


def release_input_manifest() -> str:
    """Hash immutable release inputs before any runner receives a request."""
    digest = hashlib.sha256()
    for path in (PROJECT_ROOT / "pyproject.toml", PROJECT_ROOT / "uv.lock"):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def project_python_path() -> Path:
    """Return the repository-controlled interpreter path for the active platform."""
    candidates = (
        PROJECT_ROOT / ".venv" / "Scripts" / "python.exe",
        PROJECT_ROOT / ".venv" / "bin" / "python",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[-1]


def uses_project_python() -> bool:
    """Report whether this release process uses the required repository interpreter."""
    expected = project_python_path()
    return expected.is_file() and Path(sys.executable).absolute() == expected.absolute()


def ensure_release_environment() -> bool:
    """Synchronize the locked release extra before importing packaging-only modules."""
    result = subprocess.run(
        ("uv", "sync", "--locked", "--inexact", "--extra", "release"),
        cwd=PROJECT_ROOT,
        check=False,
    )
    if result.returncode != 0:
        print("release-environment-sync-failed")
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
