"""Pure helpers shared by service lifecycle workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Union

from app.orchestration.lifecycle.commands import command_runs_service
from app.orchestration.lifecycle.ports import ServiceProcessPort
from app.orchestration.lifecycle.types import InvalidPidFileError


def parse_pid(pid_path: Path, content: str) -> Union[int, InvalidPidFileError]:
    """Parse and validate a positive PID from a technical receipt."""
    try:
        pid = int(content)
    except ValueError:
        return InvalidPidFileError(pid_path, content)
    if pid <= 0:
        return InvalidPidFileError(pid_path, content)
    return pid


def recorded_pid(
    elfie_home: Path, process_port: ServiceProcessPort
) -> Union[int, InvalidPidFileError, None]:
    """Read and parse the Core PID receipt through the platform Port."""
    content = process_port.read_receipt(elfie_home)
    if content is None:
        return None
    return parse_pid(elfie_home / "elfienest.pid", content)


def existing_service_command(
    elfie_home: Path,
    project_root: Path,
    process_port: ServiceProcessPort,
) -> tuple[int, tuple[str, ...]] | None:
    """Return the PID and command of a verified project service, if any."""
    try:
        pid_result = recorded_pid(elfie_home, process_port)
    except OSError:
        return None
    if not isinstance(pid_result, int) or not process_port.exists(pid_result):
        return None
    expected_root = project_root.resolve()
    expected_script = (expected_root / "scripts" / "serve.py").resolve()
    try:
        snapshot = process_port.inspect(pid_result)
        actual_root = snapshot.cwd.resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if actual_root != expected_root:
        return None
    if not command_runs_service(snapshot.command, actual_root, expected_script):
        return None
    return pid_result, snapshot.command


def existing_service_pid(
    elfie_home: Path,
    project_root: Path,
    command: tuple[str, ...],
    process_port: ServiceProcessPort,
) -> int | None:
    """Return the PID of a verified running project service, if any."""
    _ = command
    details = existing_service_command(elfie_home, project_root, process_port)
    return details[0] if details is not None else None
