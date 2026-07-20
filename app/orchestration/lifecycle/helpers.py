"""Small helpers shared by service lifecycle operations."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Sequence, Union

from app.orchestration.lifecycle.recovery_lock import MANAGED_START_ENV
from app.orchestration.lifecycle.types import InvalidPidFileError
from app.orchestration.lifecycle.process import (
    PID_FILENAME,
    ProcessInspector,
    command_runs_service,
)


def read_pid(pid_path: Path) -> Union[int, InvalidPidFileError]:
    """Read and validate a positive PID from a service receipt."""
    content = pid_path.read_text(encoding="utf-8").strip()
    try:
        pid = int(content)
    except ValueError:
        return InvalidPidFileError(pid_path, content)
    if pid <= 0:
        return InvalidPidFileError(pid_path, content)
    return pid


def default_launcher(command: Sequence[str], cwd: Path) -> int:
    """Launch a detached managed service process."""
    environment = os.environ.copy()
    environment[MANAGED_START_ENV] = "1"
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=environment,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return process.pid


def existing_service_command(
    elfie_home: Path,
    project_root: Path,
    inspector: ProcessInspector,
) -> tuple[int, tuple[str, ...]] | None:
    """Return the PID and command of a verified project service, if any."""
    pid_path = elfie_home / PID_FILENAME
    if not pid_path.exists():
        return None
    try:
        pid_result = read_pid(pid_path)
    except OSError:
        return None
    if isinstance(pid_result, InvalidPidFileError):
        return None
    if not inspector.exists(pid_result):
        return None
    expected_root = project_root.resolve()
    expected_script = (expected_root / "scripts" / "serve.py").resolve()
    try:
        actual_root = inspector.cwd(pid_result).resolve()
        actual_command = inspector.command(pid_result)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if actual_root != expected_root:
        return None
    if not command_runs_service(actual_command, actual_root, expected_script):
        return None
    return pid_result, tuple(actual_command)


def existing_service_pid(
    elfie_home: Path,
    project_root: Path,
    command: Sequence[str],
    inspector: ProcessInspector,
) -> int | None:
    """Return the PID of a verified running project service, if any."""
    _ = command
    details = existing_service_command(elfie_home, project_root, inspector)
    return details[0] if details is not None else None
