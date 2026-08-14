"""Process and PID receipt cleanup after service startup failure."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

from app.orchestration.lifecycle.commands import command_matches_service
from app.orchestration.lifecycle.ports import ServiceProcessPort
from app.orchestration.lifecycle.types import (
    CleanupFailedError,
    ServiceLifecycleError,
    ServiceLifecycleResult,
)


def cleanup_failed_start(
    pid: int,
    pid_path: Path,
    original_error: ServiceLifecycleError,
    process_port: ServiceProcessPort,
    expected_cwd: Path,
    expected_script: Path,
    expected_command: Sequence[str],
    timeout_seconds: float,
    poll_interval_seconds: float,
    monotonic: Callable[[], float],
    sleeper: Callable[[float], None],
) -> ServiceLifecycleResult:
    """Stop a process that failed health startup, removing only receipts still owned by that PID."""
    if not process_port.exists(pid):
        process_port.remove_receipt(pid_path.parent, pid)
        return ServiceLifecycleResult(status="failed", pid=pid, error=original_error)
    try:
        snapshot = process_port.inspect(pid)
        actual_cwd = snapshot.cwd.resolve()
        actual_command = snapshot.command
    except (OSError, RuntimeError, ValueError) as error:
        if not process_port.exists(pid):
            process_port.remove_receipt(pid_path.parent, pid)
            return ServiceLifecycleResult(
                status="failed", pid=pid, error=original_error
            )
        return ServiceLifecycleResult(
            status="failed", pid=pid, error=CleanupFailedError(pid, str(error))
        )
    if actual_cwd != expected_cwd or not command_matches_service(
        actual_command,
        actual_cwd,
        expected_script,
        expected_command,
    ):
        return ServiceLifecycleResult(
            status="failed",
            pid=pid,
            error=CleanupFailedError(
                pid, "PID has been reused by another process; refusing to send signal"
            ),
        )
    try:
        process_port.terminate(pid)
    except ProcessLookupError:
        process_port.remove_receipt(pid_path.parent, pid)
        return ServiceLifecycleResult(status="failed", pid=pid, error=original_error)
    except OSError as error:
        return ServiceLifecycleResult(
            status="failed", pid=pid, error=CleanupFailedError(pid, str(error))
        )
    deadline = monotonic() + timeout_seconds
    while process_port.exists(pid):
        if monotonic() >= deadline:
            return ServiceLifecycleResult(
                status="failed",
                pid=pid,
                error=CleanupFailedError(pid, "Process did not exit after SIGTERM"),
            )
        sleeper(poll_interval_seconds)
    process_port.remove_receipt(pid_path.parent, pid)
    return ServiceLifecycleResult(status="failed", pid=pid, error=original_error)
