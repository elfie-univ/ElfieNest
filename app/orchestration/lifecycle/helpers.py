"""Pure helpers shared by service lifecycle workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence, Union

from app.orchestration.lifecycle.commands import command_matches_service
from app.orchestration.lifecycle.ports import RuntimeRecordPort, ServiceProcessPort
from app.orchestration.lifecycle.runtime_snapshot import RuntimeComponent
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
    runtime_record: RuntimeRecordPort | None = None,
    expected_command: Sequence[str] = (),
) -> tuple[int, tuple[str, ...]] | None:
    """Return one verified service generation, if the selected root owns it."""
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
    if runtime_record is None:
        # A PID receipt without the selected Runtime snapshot is not an
        # authority.  The caller may launch only after its normal port and
        # snapshot checks; it must not attach to this process.
        return None
    try:
        runtime = runtime_record.read()
    except (OSError, RuntimeError, ValueError):
        return None
    component = runtime.component(RuntimeComponent.CORE)
    if (
        component.pid != pid_result
        or not component.birth_identity
        or not component.executable
        or not component.cwd
        or snapshot.birth_identity != component.birth_identity
        or actual_root != Path(component.cwd).resolve()
        or snapshot.cwd.resolve() != Path(component.cwd).resolve()
        or not _observed_executable_matches(snapshot.command, component.executable)
    ):
        return None
    if actual_root != expected_root:
        return None
    if not command_matches_service(
        snapshot.command,
        actual_root,
        expected_script,
        expected_command,
    ):
        return None
    return pid_result, snapshot.command


def _observed_executable_matches(
    command: Sequence[str], expected_executable: str
) -> bool:
    expected = Path(expected_executable).resolve(strict=False)
    for count in range(1, len(command) + 1):
        candidate = Path(" ".join(command[:count])).resolve(strict=False)
        if candidate == expected:
            return True
    return False
