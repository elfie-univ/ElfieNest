"""Execute one complete native release pipeline with no optional runtime stages."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Final, Optional, TypeVar

from scripts import (
    assemble_desktop_resources,
    check_release_version,
    ollama_sidecar,
    package_python_core,
    release_manifest,
)

PROJECT_ROOT: Final = Path(__file__).resolve().parents[1]
BUILD_DIR: Final = PROJECT_ROOT / "build"
DIST_DIR: Final = PROJECT_ROOT / "dist"
FRONTEND_DIR: Final = PROJECT_ROOT / "app" / "interfaces" / "web" / "frontend"
DESKTOP_DIR: Final = PROJECT_ROOT / "desktop"
StageResult = TypeVar("StageResult")


class NativeReleaseTargetError(RuntimeError):
    """Raised when a non-native runner attempts a target build."""


class ReleasePipelineError(RuntimeError):
    """Raised when a required stage cannot safely continue to packaging."""


@dataclass(frozen=True)
class NativeReleaseSteps:
    """Concrete operations for a complete native release build."""

    ensure_dependencies: Callable[[], None]
    build_web: Callable[[], None]
    build_godot: Callable[[], None]
    freeze_core: Callable[[str], Path]
    freeze_cli: Callable[[str], Path]
    download_sidecar: Callable[[str], Path]
    assemble: Callable[[str, Path, Path, Path], Path]
    validate: Callable[[Path], None]
    package: Callable[[str, Path, Dict[str, str]], Path]


def run_native_release(
    target: str,
    host_target: str,
    steps: NativeReleaseSteps,
) -> Path:
    """Run every mandatory step for one native target and return its installer."""
    if target != host_target:
        raise NativeReleaseTargetError(
            f"native-target-required target={target} host_target={host_target}"
        )
    _run_stage("web", steps.build_web)
    _run_stage("godot", steps.build_godot)
    _run_stage("dependencies", steps.ensure_dependencies)
    core = _run_stage("python-core", lambda: steps.freeze_core(target))
    cli = _run_stage("management-cli", lambda: steps.freeze_cli(target))
    archive = _run_stage("ollama-sidecar", lambda: steps.download_sidecar(target))
    resources = _run_stage(
        "resources", lambda: steps.assemble(target, core, cli, archive)
    )
    _run_stage("manifest", lambda: steps.validate(resources))
    environment = dict(os.environ)
    environment["ELFIENEST_TARGET"] = target
    return _run_stage("package", lambda: steps.package(target, resources, environment))


def _run_stage(stage: str, operation: Callable[[], StageResult]) -> StageResult:
    """Convert known build failures into a stage-labelled hard stop."""
    try:
        return operation()
    except ReleasePipelineError:
        raise
    except (
        OSError,
        subprocess.CalledProcessError,
        assemble_desktop_resources.ResourceAssemblyError,
        check_release_version.ReleaseVersionError,
        ollama_sidecar.OllamaSidecarDownloadError,
        package_python_core.NativeTargetRequiredError,
        package_python_core.OllamaSourceError,
        release_manifest.ReleaseResourceManifestError,
    ) as error:
        raise ReleasePipelineError(
            f"release-stage-failed stage={stage} cause={error}"
        ) from error


def default_release_steps() -> NativeReleaseSteps:
    """Build concrete strict operations for one local target-native release."""
    version = check_release_version.check_versions(
        DESKTOP_DIR / "package.json",
        FRONTEND_DIR / "package.json",
    )
    return NativeReleaseSteps(
        ensure_dependencies=_ensure_dependencies,
        build_web=_build_web,
        build_godot=_build_godot,
        freeze_core=_freeze_core,
        freeze_cli=_freeze_cli,
        download_sidecar=_download_sidecar,
        assemble=lambda target, core, cli, archive: _assemble(
            target, core, cli, archive, version
        ),
        validate=_validate_resources,
        package=_package_installer,
    )


def _run_command(command: tuple[str, ...], cwd: Path, environment: Optional[Dict[str, str]] = None) -> None:
    """Run one required build command, propagating nonzero exits as hard failures."""
    subprocess.run(command, cwd=cwd, env=environment, check=True)


def _ensure_dependencies() -> None:
    """Verify every production runtime input after the buildable Godot gate ran."""
    _run_command((str(PROJECT_ROOT / "scripts" / "bootstrap.sh"), "check", "--tier=prod"), PROJECT_ROOT)


def _build_web() -> None:
    """Build the product React shell using the repository-pinned pnpm release."""
    environment = {**os.environ, "CI": "true"}
    _run_command(
        (
            "npx",
            "--yes",
            "pnpm@10.12.1",
            "install",
            "--frozen-lockfile",
            "--force",
        ),
        FRONTEND_DIR,
        environment,
    )
    _run_command(
        ("npx", "--yes", "pnpm@10.12.1", "build"),
        FRONTEND_DIR,
        environment,
    )


def _build_godot() -> None:
    """Export the required Godot Web runtime through the controlled project script."""
    _run_command((_project_python(), "scripts/build_godot_web.py", "--ensure"), PROJECT_ROOT)


def _freeze_core(target: str) -> Path:
    """Freeze the Core only through the active target-native Python runner."""
    return package_python_core.freeze_core(
        target=target,
        output_dir=BUILD_DIR / "python-core" / target,
        host_target=package_python_core.host_target(),
    )


def _freeze_cli(target: str) -> Path:
    """Freeze the checkout-independent management CLI for the same native target."""
    return package_python_core.freeze_cli(
        target=target,
        output_dir=BUILD_DIR / "python-cli" / target,
        host_target=package_python_core.host_target(),
    )


def _download_sidecar(target: str) -> Path:
    """Acquire the checked-in, checksum-pinned sidecar asset for this target."""
    source = package_python_core.load_ollama_sources().for_target(target)
    return ollama_sidecar.download_sidecar(
        source=source,
        destination=BUILD_DIR / "downloads" / "ollama" / target / source.filename,
    )


def _assemble(target: str, core: Path, cli: Path, archive: Path, version: str) -> Path:
    """Assemble the one target-scoped Electron resource root."""
    source = package_python_core.load_ollama_sources().for_target(target)
    return assemble_desktop_resources.assemble_resources(
        target=target,
        output_root=BUILD_DIR / "staging",
        web_source=BUILD_DIR / "web",
        godot_source=BUILD_DIR / "components" / "godot-web",
        core_source=core,
        cli_source=cli,
        ollama_archive=archive,
        ollama_source=source,
        application_version=version,
    )


def _validate_resources(resources: Path) -> None:
    """Recompute and validate the runtime contract before Electron can consume it."""
    release_manifest.validate_release_resources(resources)


def _package_installer(target: str, resources: Path, environment: Dict[str, str]) -> Path:
    """Create one native installer in build first, then publish only a complete file."""
    if resources != BUILD_DIR / "staging" / target / "resources":
        raise ReleasePipelineError(f"release-resources-target-mismatch target={target}")
    output = BUILD_DIR / "package-output" / target
    if output.exists():
        shutil.rmtree(output)
    try:
        target_arguments = _electron_target_arguments(target)
        _run_command(
            (
                "npx",
                "--yes",
                "pnpm@10.12.1",
                "exec",
                "electron-builder",
                "--publish",
                "never",
                f"--config.directories.output={output}",
                *target_arguments,
            ),
            DESKTOP_DIR,
            environment,
        )
        artifacts = tuple(
            path for path in output.rglob(_installer_glob(target)) if path.is_file()
        )
        if len(artifacts) != 1:
            raise ReleasePipelineError(
                f"release-installer-invalid target={target} count={len(artifacts)}"
            )
        destination = DIST_DIR / artifacts[0].name
        DIST_DIR.mkdir(parents=True, exist_ok=True)
        artifacts[0].replace(destination)
        return destination
    finally:
        if output.exists():
            shutil.rmtree(output)


def _project_python() -> str:
    """Return the repository-controlled interpreter required by the release contract."""
    executable = PROJECT_ROOT / ".venv" / "bin" / "python"
    if not executable.is_file():
        raise ReleasePipelineError(f"release-python-missing path={executable}")
    return str(executable)


def _electron_target_arguments(target: str) -> tuple[str, str]:
    """Map one repository target to electron-builder's matching native flags."""
    arguments = {
        "darwin-arm64": ("--mac", "--arm64"),
        "darwin-x64": ("--mac", "--x64"),
        "win32-x64": ("--win", "--x64"),
        "linux-x64": ("--linux", "--x64"),
    }
    try:
        return arguments[target]
    except KeyError as error:
        raise ReleasePipelineError(f"release-target-unsupported target={target}") from error


def _installer_glob(target: str) -> str:
    """Return the only installer file extension valid for the native target."""
    extensions = {
        "darwin-arm64": "*.dmg",
        "darwin-x64": "*.dmg",
        "win32-x64": "*.exe",
        "linux-x64": "*.AppImage",
    }
    try:
        return extensions[target]
    except KeyError as error:
        raise ReleasePipelineError(f"release-target-unsupported target={target}") from error
