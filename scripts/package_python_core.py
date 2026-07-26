#!/usr/bin/env python3
"""Freeze the native Python Core and verify pre-downloaded Ollama sidecars."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Final, Sequence, Tuple

PROJECT_ROOT: Final = Path(__file__).resolve().parents[1]
OLLAMA_SOURCES_PATH: Final = PROJECT_ROOT / "desktop" / "packaging" / "ollama-sources.json"
PYINSTALLER_CACHE_DIR: Final = PROJECT_ROOT / "build" / "pyinstaller-cache"
TARGETS: Final[Tuple[str, ...]] = (
    "darwin-arm64",
    "darwin-x64",
    "win32-x64",
    "linux-x64",
)


class NativeTargetRequiredError(RuntimeError):
    """Raised when a runner is asked to make another platform's executable."""


class OllamaSourceError(RuntimeError):
    """Base error for immutable Ollama source provenance failures."""


class OllamaSourceChecksumError(OllamaSourceError):
    """Raised when a sidecar archive differs from its pinned SHA-256."""


@dataclass(frozen=True)
class OllamaSource:
    """An immutable official release asset usable by one desktop target."""

    target: str
    version: str
    url: str
    filename: str
    sha256: str
    license_notice: str


@dataclass(frozen=True)
class OllamaSources:
    """The checked-in set of source assets allowed into release staging."""

    entries: Tuple[OllamaSource, ...]

    def for_target(self, target: str) -> OllamaSource:
        """Return the one immutable source registered for ``target``."""
        for entry in self.entries:
            if entry.target == target:
                return entry
        raise OllamaSourceError(f"ollama-source-target-unsupported target={target}")


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


def _required_string(payload: dict, field: str) -> str:
    """Parse one required, nonempty provenance field at the JSON boundary."""
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise OllamaSourceError(f"ollama-source-invalid field={field}")
    return value


def _validate_license_notice(path_value: str) -> str:
    """Require a checked-in notice below the repository root."""
    notice = (PROJECT_ROOT / path_value).resolve()
    try:
        notice.relative_to(PROJECT_ROOT)
    except ValueError as error:
        raise OllamaSourceError(
            f"ollama-source-license-outside-repository path={path_value}"
        ) from error
    if not notice.is_file():
        raise OllamaSourceError(f"ollama-source-license-missing path={path_value}")
    return path_value


def load_ollama_sources(path: Path = OLLAMA_SOURCES_PATH) -> OllamaSources:
    """Load and validate the immutable release-sidecar source registry."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise OllamaSourceError(f"ollama-source-registry-unreadable path={path}") from error
    if not isinstance(payload, dict):
        raise OllamaSourceError("ollama-source-registry-invalid")
    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list):
        raise OllamaSourceError("ollama-source-registry-invalid field=sources")
    sources = []
    for raw_source in raw_sources:
        if not isinstance(raw_source, dict):
            raise OllamaSourceError("ollama-source-invalid entry")
        target = _required_string(raw_source, "target")
        source = OllamaSource(
            target=target,
            version=_required_string(raw_source, "version"),
            url=_required_string(raw_source, "url"),
            filename=_required_string(raw_source, "filename"),
            sha256=_required_string(raw_source, "sha256"),
            license_notice=_validate_license_notice(
                _required_string(raw_source, "license_notice")
            ),
        )
        if source.target not in TARGETS:
            raise OllamaSourceError(f"ollama-source-target-unsupported target={target}")
        if not source.url.startswith("https://github.com/ollama/ollama/releases/"):
            raise OllamaSourceError(f"ollama-source-url-untrusted target={target}")
        if len(source.sha256) != 64 or any(
            character not in "0123456789abcdef" for character in source.sha256
        ):
            raise OllamaSourceError(f"ollama-source-sha256-invalid target={target}")
        sources.append(source)
    registry = OllamaSources(entries=tuple(sources))
    if len(registry.entries) != len(TARGETS) or {
        entry.target for entry in registry.entries
    } != set(TARGETS):
        raise OllamaSourceError("ollama-source-targets-incomplete")
    return registry


def verify_ollama_source(source_path: Path, provenance: OllamaSource) -> None:
    """Verify a pre-downloaded sidecar archive before any staging can consume it."""
    if source_path.name != provenance.filename:
        raise OllamaSourceError(
            "ollama-source-filename-mismatch "
            f"expected={provenance.filename} actual={source_path.name}"
        )
    digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if digest != provenance.sha256:
        raise OllamaSourceChecksumError(
            "ollama-source-checksum-mismatch "
            f"target={provenance.target} expected={provenance.sha256} actual={digest}"
        )


def parse_args() -> argparse.Namespace:
    """Parse the local-only Core freeze and sidecar verification commands."""
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    freeze = subcommands.add_parser("freeze-core")
    freeze.add_argument("--target", required=True, choices=TARGETS)
    freeze.add_argument("--output-dir", required=True, type=Path)
    verify = subcommands.add_parser("verify-ollama")
    verify.add_argument("--target", required=True, choices=TARGETS)
    verify.add_argument("--source", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    """Execute a target-native freeze or local sidecar provenance check."""
    args = parse_args()
    try:
        if args.command == "freeze-core":
            artifact = freeze_core(args.target, args.output_dir, host_target())
            print(f"python-core-freeze-ok artifact={artifact}")
        elif args.command == "verify-ollama":
            source = load_ollama_sources().for_target(args.target)
            verify_ollama_source(args.source, source)
            print(f"ollama-source-verified target={source.target} source={args.source}")
        else:
            raise RuntimeError(f"unknown command {args.command}")
    except (NativeTargetRequiredError, OllamaSourceError, OSError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
