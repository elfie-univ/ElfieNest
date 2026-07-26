"""Resolve installed runtime siblings for the frozen management CLI."""

from __future__ import annotations

from pathlib import Path
from typing import MutableMapping


class PackagedCliRuntimeError(RuntimeError):
    """Raised when a frozen CLI cannot locate its packaged Core sibling."""


def configure_frozen_cli_runtime(
    executable: Path,
    platform: str,
    environment: MutableMapping[str, str],
) -> None:
    """Set the Core path from the installed resource layout, never a source checkout."""
    executable_names = {"win32": "ElfieNestCore.exe", "darwin": "ElfieNestCore", "linux": "ElfieNestCore"}
    try:
        core_name = executable_names[platform]
    except KeyError as error:
        raise PackagedCliRuntimeError(
            f"packaged-cli-platform-unsupported platform={platform}"
        ) from error
    core = executable.parent.parent / "python-core" / core_name
    if not core.is_file():
        raise PackagedCliRuntimeError(f"packaged-cli-core-missing path={core}")
    environment["ELFIENEST_CORE_BIN"] = str(core)
