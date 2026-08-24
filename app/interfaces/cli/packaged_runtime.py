"""Resolve installed runtime siblings for the frozen management CLI."""

from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
from typing import Final, Mapping, MutableMapping, NamedTuple


class PackagedCliRuntimeError(RuntimeError):
    """Raised when a frozen CLI cannot locate its packaged Core sibling."""


class RuntimeInstallContractError(ValueError):
    """Raised when runtime-installation provenance crosses the wrong boundary."""


class RuntimeState(str, Enum):
    """The only two ways ElfieNest may execute."""

    SOURCE_DEVELOPMENT = "source_development"
    INSTALLED_RUNTIME = "installed_runtime"


class InstallMethod(str, Enum):
    """The supported application installation provenance."""

    MANUAL_NATIVE_PACKAGE = "manual_native_package"


class NativeTarget(str, Enum):
    """Supported release targets with one canonical installed layout each."""

    DARWIN_ARM64 = "darwin-arm64"
    DARWIN_X64 = "darwin-x64"
    WIN32_X64 = "win32-x64"
    LINUX_X64 = "linux-x64"


class InstalledApplicationLayout(NamedTuple):
    """Canonical application root and its packaged management CLI path."""

    application_root: Path
    management_cli: Path


class InstalledRuntimeRecord(NamedTuple):
    """The provenance of an application that has entered installed runtime."""

    runtime_state: RuntimeState
    install_method: InstallMethod


class InstalledRuntimeSurface(NamedTuple):
    """The installed manifest and Setup entry for a native app package."""

    record: InstalledRuntimeRecord
    manifest_path: Path
    setup_path: str


_APPLICATION_ROOT_TEMPLATES: Final[Mapping[NativeTarget, str]] = {
    NativeTarget.DARWIN_ARM64: "/Applications/ElfieNest.app",
    NativeTarget.DARWIN_X64: "/Applications/ElfieNest.app",
    NativeTarget.WIN32_X64: "{local_app_data}/Programs/ElfieNest",
    NativeTarget.LINUX_X64: "{home_directory}/.local/opt/ElfieNest",
}
_MANAGEMENT_CLI_RELATIVE_PATHS: Final[Mapping[NativeTarget, Path]] = {
    NativeTarget.DARWIN_ARM64: Path("Contents/Resources/management-cli/ElfieNestCli"),
    NativeTarget.DARWIN_X64: Path("Contents/Resources/management-cli/ElfieNestCli"),
    NativeTarget.WIN32_X64: Path("resources/management-cli/ElfieNestCli.exe"),
    NativeTarget.LINUX_X64: Path("resources/management-cli/ElfieNestCli"),
}
_RESOURCE_ROOT_RELATIVE_PATHS: Final[Mapping[NativeTarget, Path]] = {
    NativeTarget.DARWIN_ARM64: Path("Contents/Resources"),
    NativeTarget.DARWIN_X64: Path("Contents/Resources"),
    NativeTarget.WIN32_X64: Path("resources"),
    NativeTarget.LINUX_X64: Path("resources"),
}
_SETUP_PATH: Final[str] = "/setup"


def packaged_application_version(executable: Path) -> str | None:
    """Read an installed CLI's release version from its adjacent resource manifest."""
    manifest_path = executable.parent.parent / "manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    version = payload.get("application_version")
    return version if isinstance(version, str) and version else None


def parse_runtime_state(value: str) -> RuntimeState:
    """Parse a runtime state without accepting installation-method values."""
    try:
        return RuntimeState(value)
    except ValueError as error:
        raise RuntimeInstallContractError(
            f"runtime-state-invalid value={value}"
        ) from error


def parse_install_method(value: str) -> InstallMethod:
    """Parse application-install provenance without accepting runtime states."""
    try:
        return InstallMethod(value)
    except ValueError as error:
        raise RuntimeInstallContractError(
            f"install-method-invalid value={value}"
        ) from error


def canonical_installed_layout(
    target: NativeTarget,
    *,
    home_directory: Path,
    local_app_data: Path,
) -> InstalledApplicationLayout:
    """Resolve the target's one application root and in-app management CLI."""
    application_root = Path(
        _APPLICATION_ROOT_TEMPLATES[target].format(
            home_directory=home_directory,
            local_app_data=local_app_data,
        )
    )
    return InstalledApplicationLayout(
        application_root=application_root,
        management_cli=application_root / _MANAGEMENT_CLI_RELATIVE_PATHS[target],
    )


def installed_runtime_record(install_method: InstallMethod) -> InstalledRuntimeRecord:
    """Record installation provenance without creating another runtime state."""
    return InstalledRuntimeRecord(
        runtime_state=RuntimeState.INSTALLED_RUNTIME,
        install_method=install_method,
    )


def installed_runtime_surface(
    *,
    install_method: InstallMethod,
    target: NativeTarget,
    home_directory: Path,
    local_app_data: Path,
) -> InstalledRuntimeSurface:
    """Resolve the common installed manifest and Setup entry for one provenance."""
    layout = canonical_installed_layout(
        target,
        home_directory=home_directory,
        local_app_data=local_app_data,
    )
    return InstalledRuntimeSurface(
        record=installed_runtime_record(install_method),
        manifest_path=(
            layout.application_root
            / _RESOURCE_ROOT_RELATIVE_PATHS[target]
            / "manifest.json"
        ),
        setup_path=_SETUP_PATH,
    )


def configure_frozen_cli_runtime(
    executable: Path,
    platform: str,
    environment: MutableMapping[str, str],
) -> None:
    """Set the Core path from the installed resource layout, never a source checkout."""
    executable_names = {
        "win32": "ElfieNestCore.exe",
        "darwin": "ElfieNestCore",
        "linux": "ElfieNestCore",
    }
    try:
        core_name = executable_names[platform]
    except KeyError as error:
        raise PackagedCliRuntimeError(
            f"packaged-cli-platform-unsupported platform={platform}"
        ) from error
    resources = executable.parent.parent
    core = resources / "python-core" / core_name
    if not core.is_file():
        raise PackagedCliRuntimeError(f"packaged-cli-core-missing path={core}")
    desktop_executables = {
        "win32": resources.parent / "ElfieNest.exe",
        "darwin": resources.parent / "MacOS" / "ElfieNest",
        "linux": resources.parent / "elfienest-gui",
    }
    desktop = desktop_executables[platform]
    world_runtime: Path | None = None
    if platform == "linux":
        world_runtime = resources / "godot-linux-dedicated" / "ElfieNestRuntime"
        if not world_runtime.is_file() or not os.access(world_runtime, os.X_OK):
            raise PackagedCliRuntimeError(
                f"packaged-cli-world-runtime-missing path={world_runtime}"
            )
    application_root = (
        resources.parent.parent if platform == "darwin" else resources.parent
    )
    runtime_environment = {
        "ELFIENEST_CORE_BIN": str(core),
        "ELFIENEST_WEB_BUILD_DIR": str(resources / "web"),
        "ELFIENEST_GODOT_WEB_DIR": str(resources / "godot-web"),
        "ELFIENEST_BUNDLED_CONFIG_DIR": str(resources / "config"),
        "ELFIENEST_RUNTIME_MODE": "release",
        "ELFIENEST_PROJECT_ROOT": str(application_root),
        "ELFIENEST_DESKTOP_BIN": str(desktop),
        "PYINSTALLER_RESET_ENVIRONMENT": "1",
    }
    if world_runtime is not None:
        runtime_environment["ELFIENEST_RUNTIME_BIN"] = str(world_runtime)
    environment.update(runtime_environment)
