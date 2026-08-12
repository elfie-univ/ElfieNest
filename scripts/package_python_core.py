#!/usr/bin/env python3
"""Freeze native Core and management CLI executables for one release target."""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Callable, Final, Sequence, Tuple

PROJECT_ROOT: Final = Path(__file__).resolve().parents[1]
PYINSTALLER_CACHE_DIR: Final = PROJECT_ROOT / "build" / "pyinstaller-cache"
TARGETS: Final[Tuple[str, ...]] = (
    "darwin-arm64",
    "darwin-x64",
    "win32-x64",
    "linux-x64",
)


class NativeTargetRequiredError(RuntimeError):
    """Raised when a runner is asked to make another platform's executable."""


def host_target() -> str:
    """Return the release target represented by the active native runner."""
    platform_name = sys.platform
    machine = platform.machine().lower()
    if platform_name == "darwin":
        if machine in ("arm64", "aarch64"):
            return "darwin-arm64"
        if machine == "x86_64":
            return "darwin-x64"
    if platform_name == "win32" and machine in ("amd64", "x86_64"):
        return "win32-x64"
    if platform_name.startswith("linux") and machine in ("amd64", "x86_64"):
        return "linux-x64"
    raise NativeTargetRequiredError(
        f"native-target-unsupported platform={platform_name} machine={machine}"
    )


def executable_name(target: str) -> str:
    """Return the platform-specific frozen Core executable filename."""
    if target not in TARGETS:
        raise NativeTargetRequiredError(f"native-target-unsupported target={target}")
    return "ElfieNestCore.exe" if target == "win32-x64" else "ElfieNestCore"


def cli_executable_name(target: str) -> str:
    """Return the platform-specific frozen management CLI filename."""
    if target not in TARGETS:
        raise NativeTargetRequiredError(f"native-target-unsupported target={target}")
    return "ElfieNestCli.exe" if target == "win32-x64" else "ElfieNestCli"


def _run_pyinstaller(command: Sequence[str]) -> None:
    """Run PyInstaller without allowing a failed process to create an artifact."""
    PYINSTALLER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        command,
        check=True,
        env={**os.environ, "PYINSTALLER_CONFIG_DIR": str(PYINSTALLER_CACHE_DIR)},
    )


def freeze_core(
    target: str,
    output_dir: Path,
    host_target: str,
    command_runner: Callable[[Sequence[str]], None] = _run_pyinstaller,
) -> Path:
    """Freeze the source Core only when the build runner is target-native."""
    return _freeze_entrypoint(
        target=target,
        output_dir=output_dir,
        host_target=host_target,
        executable=executable_name(target),
        entrypoint=PROJECT_ROOT / "scripts" / "serve.py",
        command_runner=command_runner,
    )


def freeze_cli(
    target: str,
    output_dir: Path,
    host_target: str,
    command_runner: Callable[[Sequence[str]], None] = _run_pyinstaller,
) -> Path:
    """Freeze the management CLI so installed commands never use a checkout path."""
    return _freeze_entrypoint(
        target=target,
        output_dir=output_dir,
        host_target=host_target,
        executable=cli_executable_name(target),
        entrypoint=PROJECT_ROOT / "scripts" / "elfienest.py",
        command_runner=command_runner,
    )


def _freeze_entrypoint(
    target: str,
    output_dir: Path,
    host_target: str,
    executable: str,
    entrypoint: Path,
    command_runner: Callable[[Sequence[str]], None],
) -> Path:
    """Freeze one native executable with the common PyInstaller contract."""
    if target != host_target:
        raise NativeTargetRequiredError(
            f"native-target-required target={target} host_target={host_target}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    command = (
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--collect-data",
        "infrastructure.models.providers",
        "--name",
        executable.rsplit(".", 1)[0],
        "--distpath",
        str(output_dir),
        "--workpath",
        str(output_dir.parent / "pyinstaller-work"),
        "--specpath",
        str(output_dir.parent / "pyinstaller-spec"),
        str(entrypoint),
    )
    command_runner(command)
    return output_dir / executable


def parse_args() -> argparse.Namespace:
    """Parse the local-only Core freeze command."""
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    freeze = subcommands.add_parser("freeze-core")
    freeze.add_argument("--target", required=True, choices=TARGETS)
    freeze.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    """Execute a target-native Core freeze."""
    args = parse_args()
    try:
        if args.command == "freeze-core":
            artifact = freeze_core(args.target, args.output_dir, host_target())
            print(f"python-core-freeze-ok artifact={artifact}")
        else:
            raise RuntimeError(f"unknown command {args.command}")
    except (NativeTargetRequiredError, OSError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
