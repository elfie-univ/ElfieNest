#!/usr/bin/env python3
"""Coordinate strict native release builds without publishing artifacts."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Final, Optional, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import package_python_core
from scripts.release_planning import ReleasePlan, ReleasePlanError, plan_release

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
        help="write the one locally built artifact path for an installer caller",
    )
    return parser.parse_args(arguments)


def main(arguments: Optional[Sequence[str]] = None) -> int:
    """Report the native work executable here and the runners still required."""
    args = parse_args(arguments)
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
            from scripts import release_pipeline
        except ImportError as error:
            print(f"release-dependency-missing module={error.name}")
            return 1

    try:
        artifacts = []
        if plan.native_targets:
            steps = release_pipeline.default_release_steps()
        for target in plan.native_targets:
            artifact = release_pipeline.run_native_release(
                target=target,
                host_target=package_python_core.host_target(),
                steps=steps,
            )
            artifacts.append(artifact)
            print(f"release-target-built target={target} artifact={artifact}")
    except (release_pipeline.ReleasePipelineError, release_pipeline.NativeReleaseTargetError) as error:
        print(str(error))
        return 1
    if args.artifact_output is not None:
        if len(artifacts) != 1 or not plan.is_complete:
            print("release-artifact-output-requires-one-complete-native-target")
            return 2
        args.artifact_output.write_text(f"{artifacts[0].resolve()}\n", encoding="utf-8")
    _print_missing_runner_targets(plan)
    return 0 if plan.is_complete else 3


def _print_missing_runner_targets(plan: ReleasePlan) -> None:
    """Report incomplete cross-runner work without disguising it as a release."""
    for target in plan.requires_native_runner:
        print(f"release-target-requires-native-runner target={target}")


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
