"""Process and PID receipt cleanup after service startup failure."""

from __future__ import annotations

import signal
import subprocess
from pathlib import Path
from typing import Callable

from app.orchestration.lifecycle.process import (
    ProcessInspector,
    command_runs_service,
    remove_service_process,
)
from app.orchestration.lifecycle.types import (
    CleanupFailedError,
    ServiceLifecycleError,
    ServiceLifecycleResult,
)


def cleanup_failed_start(
    pid: int,
    pid_path: Path,
    original_error: ServiceLifecycleError,
    inspector: ProcessInspector,
    signaler: Callable[[int, int], None],
    expected_cwd: Path,
    expected_script: Path,
    timeout_seconds: float,
    poll_interval_seconds: float,
    monotonic: Callable[[], float],
    sleeper: Callable[[float], None],
) -> ServiceLifecycleResult:
    """Stop a process that failed health startup, removing only receipts still owned by that PID."""
    if not inspector.exists(pid):
        remove_service_process(pid_path.parent, pid)
        return ServiceLifecycleResult(status="failed", pid=pid, error=original_error)
    try:
        actual_cwd = inspector.cwd(pid).resolve()
        actual_command = inspector.command(pid)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        if not inspector.exists(pid):
            remove_service_process(pid_path.parent, pid)
            return ServiceLifecycleResult(
                status="failed", pid=pid, error=original_error
            )
        return ServiceLifecycleResult(
            status="failed", pid=pid, error=CleanupFailedError(pid, str(error))
        )
    if actual_cwd != expected_cwd or not command_runs_service(
        actual_command, actual_cwd, expected_script
    ):
        return ServiceLifecycleResult(
            status="failed",
            pid=pid,
            error=CleanupFailedError(
                pid, "PID has been reused by another process; refusing to send signal"
            ),
        )
    try:
        signaler(pid, signal.SIGTERM)
    except ProcessLookupError:
        remove_service_process(pid_path.parent, pid)
        return ServiceLifecycleResult(status="failed", pid=pid, error=original_error)
    except OSError as error:
        return ServiceLifecycleResult(
            status="failed", pid=pid, error=CleanupFailedError(pid, str(error))
        )
    deadline = monotonic() + timeout_seconds
    while inspector.exists(pid):
        if monotonic() >= deadline:
            return ServiceLifecycleResult(
                status="failed",
                pid=pid,
                error=CleanupFailedError(pid, "Process did not exit after SIGTERM"),
            )
        sleeper(poll_interval_seconds)
    remove_service_process(pid_path.parent, pid)
    return ServiceLifecycleResult(status="failed", pid=pid, error=original_error)
