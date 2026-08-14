"""Freshness checks and pinned builds for the source Web client."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Callable, Final, Optional, Sequence

from app.orchestration.lifecycle import FrontendPreparationError

PROJECT_ROOT: Final = Path(__file__).resolve().parents[2]
FRONTEND_SOURCE_DIRECTORY: Final = (
    PROJECT_ROOT / "app" / "interfaces" / "web" / "frontend"
)
WEB_BUILD_DIRECTORY: Final = PROJECT_ROOT / "build" / "web"
BUILD_MANIFEST_NAME: Final = "build-manifest.json"
PNPM_VERSION: Final = "10.12.1"


class FrontendBuildError(RuntimeError):
    """Raised when the source frontend cannot be rebuilt and verified."""


def source_digest(source: Path) -> str:
    """Return a stable digest for all frontend inputs except dependency caches."""
    digest = hashlib.sha256()
    for path in _source_files(source):
        digest.update(path.relative_to(source).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def bundle_is_current(
    output: Path,
    source: Path,
    *,
    verify_build: Callable[[Path], object],
) -> bool:
    """Return whether a generated Vite shell records the current source digest."""
    if not source.is_dir():
        return False
    marker_path = output / BUILD_MANIFEST_NAME
    if not (output / "index.html").is_file() or not marker_path.is_file():
        return False
    try:
        verify_build(output)
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return False
    if not isinstance(marker, dict):
        return False
    recorded_digest = marker.get("source_digest")
    if not isinstance(recorded_digest, str):
        return False
    try:
        current_digest = source_digest(source)
    except OSError:
        return False
    return recorded_digest == current_digest


def ensure_frontend_build(
    *,
    runtime_mode: str,
    source: Optional[Path] = None,
    output: Optional[Path] = None,
    verify_build: Callable[[Path], object],
) -> None:
    """Build the source frontend only when an actual development launch needs it."""
    if runtime_mode != "development":
        return

    source_directory = source or FRONTEND_SOURCE_DIRECTORY
    output_directory = output or WEB_BUILD_DIRECTORY
    if not source_directory.is_dir():
        raise FrontendBuildError(
            f"Frontend source directory does not exist: {source_directory}"
        )
    if bundle_is_current(
        output_directory,
        source_directory,
        verify_build=verify_build,
    ):
        return

    try:
        requested_digest = source_digest(source_directory)
    except OSError as error:
        raise FrontendBuildError(
            f"Could not read frontend source files: {error}"
        ) from error
    _run_pnpm(source_directory, ("install", "--frozen-lockfile"))
    _run_pnpm(source_directory, ("build",))
    try:
        completed_digest = source_digest(source_directory)
    except OSError as error:
        raise FrontendBuildError(
            f"Could not read frontend source files after build: {error}"
        ) from error
    if completed_digest != requested_digest:
        raise FrontendBuildError(
            "Frontend source changed during build; run the launch command again"
        )
    try:
        _write_build_marker(output_directory, completed_digest)
    except OSError as error:
        raise FrontendBuildError(
            f"Could not record frontend build state: {error}"
        ) from error
    if not bundle_is_current(
        output_directory,
        source_directory,
        verify_build=verify_build,
    ):
        raise FrontendBuildError(
            "Frontend build completed but the generated Web shell could not be verified"
        )


def _run_pnpm(frontend_root: Path, arguments: Sequence[str]) -> None:
    """Run the package-manager version declared by the frontend package."""
    command_prefix = _resolve_pnpm_command(frontend_root)
    command = (*command_prefix, *arguments)
    try:
        if os.environ.get("ELFIENEST_INTERACTIVE") == "1":
            subprocess.run(
                command,
                cwd=frontend_root,
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            subprocess.run(command, cwd=frontend_root, check=True)
    except OSError as error:
        raise FrontendBuildError(
            f"Could not run frontend build command: {error}"
        ) from error
    except subprocess.CalledProcessError as error:
        output = "\n".join(
            value.strip()
            for value in (error.stderr, error.stdout)
            if isinstance(value, str) and value.strip()
        )
        output_lines = [line for line in output.splitlines() if line.strip()]
        if len(output_lines) > 8:
            output_lines = output_lines[-8:]
        diagnostic = "\n".join(output_lines)
        if len(diagnostic) > 2000:
            diagnostic = diagnostic[-2000:]
        suffix = f":\n{diagnostic}" if diagnostic else ""
        raise FrontendBuildError(
            f"Frontend command {' '.join(arguments)} failed with exit code {error.returncode}{suffix}"
        ) from error


def _resolve_pnpm_command(frontend_root: Path) -> tuple[str, ...]:
    """Use a matching local pnpm before falling back to the network-backed npx path."""
    pnpm = shutil.which("pnpm")
    if pnpm is not None:
        try:
            version = subprocess.run(
                (pnpm, "--version"),
                cwd=frontend_root,
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError):
            pass
        else:
            if version.stdout.strip() == PNPM_VERSION:
                return (pnpm,)

    npx = shutil.which("npx")
    if npx is None:
        raise FrontendBuildError(
            f"pnpm {PNPM_VERSION} is unavailable and npx was not found; cannot build the frontend"
        )
    return (npx, "--yes", f"pnpm@{PNPM_VERSION}")


def _write_build_marker(output: Path, digest: str) -> None:
    output.mkdir(parents=True, exist_ok=True)
    marker = {"source_digest": digest}
    (output / BUILD_MANIFEST_NAME).write_text(
        json.dumps(marker, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _source_files(source: Path) -> Iterable[Path]:
    """Yield frontend inputs while excluding local dependency caches."""
    for path in sorted(source.rglob("*")):
        if path.is_file() and "node_modules" not in path.parts:
            yield path


class FrontendBuildAdapter:
    """Infrastructure implementation of lifecycle-owned frontend preparation."""

    def __init__(self, verify_build: Callable[[Path], object]) -> None:
        self._verify_build = verify_build

    def prepare(self, runtime_mode: str) -> None:
        try:
            ensure_frontend_build(
                runtime_mode=runtime_mode,
                verify_build=self._verify_build,
            )
        except FrontendBuildError as error:
            raise FrontendPreparationError(str(error)) from error
