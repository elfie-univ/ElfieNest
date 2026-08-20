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
    package_python_core,
    release_manifest,
)

PROJECT_ROOT: Final = Path(__file__).resolve().parents[1]
BUILD_DIR: Final = PROJECT_ROOT / "build"
DIST_DIR: Final = PROJECT_ROOT / "dist"
FRONTEND_DIR: Final = PROJECT_ROOT / "app" / "interfaces" / "web" / "frontend"
DESKTOP_DIR: Final = PROJECT_ROOT / "app" / "interfaces" / "desktop"
DESKTOP_HOST_CONFIG: Final = (
    PROJECT_ROOT / "app" / "bootstrap" / "desktop_host" / "electron-builder.yml"
)
DESKTOP_HOST_MAIN: Final = (
    PROJECT_ROOT / "app" / "bootstrap" / "desktop_host" / "host_main.mjs"
)
DESKTOP_AUTHORITY_DIR: Final = (
    PROJECT_ROOT / "infrastructure" / "godot" / "lifecycle" / "electron"
)
DESKTOP_PACKAGING_DIR: Final = (
    PROJECT_ROOT / "app" / "bootstrap" / "desktop_host" / "packaging"
)
MACOS_RELEASE_SIGNING_FLAG: Final = "ELFIENEST_REQUIRE_MACOS_SIGNING"
MACOS_RELEASE_CREDENTIALS: Final = (
    "CSC_LINK",
    "CSC_KEY_PASSWORD",
    "CSC_INSTALLER_LINK",
    "CSC_INSTALLER_KEY_PASSWORD",
    "APPLE_API_KEY",
    "APPLE_API_KEY_ID",
    "APPLE_API_ISSUER",
)
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
    assemble: Callable[[str, Path, Path], Path]
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
    resources = _run_stage("resources", lambda: steps.assemble(target, core, cli))
    _run_stage("manifest", lambda: steps.validate(resources))
    environment = dict(os.environ)
    environment["ELFIENEST_TARGET"] = target
    environment["ELFIENEST_PROJECT_ROOT"] = str(PROJECT_ROOT)
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
        package_python_core.NativeTargetRequiredError,
        release_manifest.ReleaseResourceManifestError,
    ) as error:
        raise ReleasePipelineError(
            f"release-stage-failed stage={stage} cause={error}"
        ) from error


def default_release_steps(*, prebuilt_godot_web: bool = False) -> NativeReleaseSteps:
    """Build concrete strict operations for one local target-native release."""
    version = check_release_version.check_versions(
        DESKTOP_DIR / "package.json",
        FRONTEND_DIR / "package.json",
    )
    return NativeReleaseSteps(
        ensure_dependencies=_ensure_dependencies,
        build_web=_build_web,
        build_godot=_check_godot if prebuilt_godot_web else _build_godot,
        freeze_core=_freeze_core,
        freeze_cli=_freeze_cli,
        assemble=lambda target, core, cli: _assemble(target, core, cli, version),
        validate=_validate_resources,
        package=_package_installer,
    )


def _run_command(
    command: tuple[str, ...], cwd: Path, environment: Optional[Dict[str, str]] = None
) -> None:
    """Run one required build command, propagating nonzero exits as hard failures."""
    subprocess.run(command, cwd=cwd, env=environment, check=True)


def _ensure_dependencies() -> None:
    """Verify every production runtime input after the buildable Godot gate ran."""
    _run_command(
        _bash_script_command(
            PROJECT_ROOT / "scripts" / "bootstrap.sh", "check", "--tier=build"
        ),
        PROJECT_ROOT,
    )


def _bash_script_command(script: Path, *arguments: str) -> tuple[str, ...]:
    """Build a Git-Bash-compatible command for shell-based repository tooling."""
    bash = shutil.which("bash") or "bash"
    script_path = str(script)
    if os.name == "nt":
        cygpath = shutil.which("cygpath")
        if cygpath is not None:
            converted = subprocess.run(
                (cygpath, "--unix", script_path),
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            if converted:
                script_path = converted
    return (bash, script_path, *arguments)


def _node_command(command: str, *arguments: str) -> tuple[str, ...]:
    """Resolve npm shims on Windows while preserving POSIX command names in tests."""
    executable = f"{command}.cmd" if os.name == "nt" and command == "npx" else command
    return (executable, *arguments)


def _build_web() -> None:
    """Build the product React shell using the repository-pinned pnpm release."""
    environment = {**os.environ, "CI": "true"}
    _run_command(
        _node_command(
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
        _node_command("npx", "--yes", "pnpm@10.12.1", "build"),
        FRONTEND_DIR,
        environment,
    )


def _build_godot() -> None:
    """Export the required Godot Web runtime through the controlled project script."""
    _run_command(
        (_project_python(), "scripts/build_godot_web.py", "--ensure"), PROJECT_ROOT
    )


def _check_godot() -> None:
    """Validate the shared Godot Web runtime without requiring a local Godot editor."""
    _run_command(
        (_project_python(), "scripts/build_godot_web.py", "--check"), PROJECT_ROOT
    )


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


def _assemble(target: str, core: Path, cli: Path, version: str) -> Path:
    """Assemble the one target-scoped Electron resource root."""
    return assemble_desktop_resources.assemble_resources(
        target=target,
        output_root=BUILD_DIR / "staging",
        web_source=BUILD_DIR / "web",
        godot_source=BUILD_DIR / "components" / "godot-web",
        core_source=core,
        cli_source=cli,
        config_source=PROJECT_ROOT / "config",
        application_version=version,
    )


def _validate_resources(resources: Path) -> None:
    """Recompute and validate the runtime contract before Electron can consume it."""
    release_manifest.validate_release_resources(resources)


def _package_installer(
    target: str, resources: Path, environment: Dict[str, str]
) -> Path:
    """Create one native installer in build first, then publish only a complete file."""
    environment = {
        **environment,
        "ELFIENEST_PROJECT_ROOT": str(PROJECT_ROOT),
    }
    if resources != BUILD_DIR / "staging" / target / "resources":
        raise ReleasePipelineError(f"release-resources-target-mismatch target={target}")
    macos_release_arguments = _macos_release_builder_arguments(target, environment)
    output = BUILD_DIR / "package-output" / target
    application = BUILD_DIR / "desktop-host-app" / target
    if output.exists():
        shutil.rmtree(output)
    try:
        _run_command(
            _node_command(
                "npx", "--yes", "pnpm@10.12.1", "install", "--frozen-lockfile"
            ),
            DESKTOP_DIR,
            environment,
        )
        _run_command(
            _node_command("npx", "--yes", "pnpm@10.12.1", "build"),
            DESKTOP_DIR,
            environment,
        )
        _stage_desktop_application(target, resources)
        target_arguments = _electron_target_arguments(target)
        _run_command(
            _node_command(
                "npx",
                "--yes",
                "pnpm@10.12.1",
                "--dir",
                str(DESKTOP_DIR),
                "exec",
                "electron-builder",
                "--projectDir",
                str(application),
                "--publish",
                "never",
                "--config",
                str(DESKTOP_HOST_CONFIG),
                f"--config.directories.output={output}",
                *macos_release_arguments,
                *target_arguments,
            ),
            application,
            environment,
        )
        artifacts = _installer_artifacts(output, target)
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
        if application.exists():
            shutil.rmtree(application)


def _macos_release_builder_arguments(
    target: str, environment: Dict[str, str]
) -> tuple[str, ...]:
    """Fail closed for formal macOS releases while preserving local unsigned builds."""
    if not target.startswith("darwin-"):
        return ()
    policy = environment.get(MACOS_RELEASE_SIGNING_FLAG)
    if policy is None:
        return ()
    if policy != "1":
        raise ReleasePipelineError(
            "macos-release-signing-policy-invalid "
            f"variable={MACOS_RELEASE_SIGNING_FLAG}"
        )
    missing = tuple(
        name for name in MACOS_RELEASE_CREDENTIALS if not environment.get(name)
    )
    if missing:
        raise ReleasePipelineError(
            "macos-release-credentials-missing variables=" + ",".join(missing)
        )
    api_key = Path(environment["APPLE_API_KEY"])
    if not api_key.is_absolute() or not api_key.is_file():
        raise ReleasePipelineError("macos-release-api-key-file-invalid")
    return (
        "--config.forceCodeSigning=true",
        "--config.mac.hardenedRuntime=true",
        "--config.mac.notarize=true",
    )


def _stage_desktop_application(target: str, resources: Path) -> Path:
    """Assemble one self-contained Electron application input under build/."""
    application = BUILD_DIR / "desktop-host-app" / target
    if application.exists():
        shutil.rmtree(application)
    application.mkdir(parents=True)

    shutil.copytree(
        BUILD_DIR / "components" / "desktop-interface",
        application / "desktop-interface",
    )
    bootstrap = application / "bootstrap"
    bootstrap.mkdir()
    shutil.copy2(DESKTOP_HOST_MAIN, bootstrap / "desktop_host.mjs")
    shutil.copytree(
        DESKTOP_AUTHORITY_DIR,
        application / "infrastructure" / "godot" / "lifecycle" / "electron",
    )
    shutil.copytree(DESKTOP_PACKAGING_DIR, application / "packaging")
    shutil.copy2(DESKTOP_DIR / "package.json", application / "package.json")
    shutil.copytree(DESKTOP_DIR / "assets", application / "assets")
    shutil.copy2(
        PROJECT_ROOT / "docs/public/assets/elfienest-logo-mark-transparent.png",
        application / "assets/elfienest-tray-icon.png",
    )
    shutil.copytree(
        resources,
        application / "packaged-resources",
        symlinks=True,
    )
    return application


def _project_python() -> str:
    """Return the repository-controlled interpreter required by the release contract."""
    candidates = (
        PROJECT_ROOT / ".venv" / "Scripts" / "python.exe",
        PROJECT_ROOT / ".venv" / "Scripts" / "python",
        PROJECT_ROOT / ".venv" / "bin" / "python3",
        PROJECT_ROOT / ".venv" / "bin" / "python",
    )
    for executable in candidates:
        if executable.is_file():
            return str(executable)
    raise ReleasePipelineError(
        "release-python-missing "
        + " ".join(f"path={candidate}" for candidate in candidates)
    )


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
        raise ReleasePipelineError(
            f"release-target-unsupported target={target}"
        ) from error


def _installer_glob(target: str) -> str:
    """Return the only installer file extension valid for the native target."""
    extensions = {
        "darwin-arm64": "*.pkg",
        "darwin-x64": "*.pkg",
        "win32-x64": "*.exe",
        "linux-x64": "*.deb",
    }
    try:
        return extensions[target]
    except KeyError as error:
        raise ReleasePipelineError(
            f"release-target-unsupported target={target}"
        ) from error


def _installer_artifacts(output: Path, target: str) -> tuple[Path, ...]:
    """Return only final top-level installers, never builder work executables."""
    return tuple(
        sorted(
            path
            for path in output.glob(_installer_glob(target))
            if path.is_file() and not path.name.endswith(".__uninstaller.exe")
        )
    )
