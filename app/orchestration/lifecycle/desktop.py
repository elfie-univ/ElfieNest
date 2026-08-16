"""Lifecycle workflow for packaged ElfieNest Desktop."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional, Sequence

from app.orchestration.lifecycle.ports import DesktopHostPort, DesktopProcess
from app.orchestration.lifecycle.types import (
    LaunchFailedError,
    ServiceLifecycleResult,
    StopTimeoutError,
)


def start_desktop_application(
    elfie_home: Path,
    project_root: Path,
    *,
    host: DesktopHostPort,
    command: Optional[Sequence[str]] = None,
    health_checker: Callable[[], bool],
    timeout_seconds: float = 30.0,
    poll_interval_seconds: float = 0.2,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> ServiceLifecycleResult:
    """Start a complete service supervised by Electron."""
    existing_pid = host.process_id(elfie_home)
    if existing_pid is not None:
        return ServiceLifecycleResult(status="already_running", pid=existing_pid)
    executable = host.find_executable(project_root)
    launch_command = (
        tuple(command)
        if command is not None
        else ((str(executable),) if executable else ())
    )
    if not launch_command:
        return ServiceLifecycleResult(
            status="failed",
            error=LaunchFailedError(
                "ElfieNest Desktop not found; please build desktop app first"
            ),
        )
    try:
        process = host.launch(launch_command, project_root)
        host.write_receipt(elfie_home, process.pid)
    except OSError as error:
        return ServiceLifecycleResult(
            status="failed", error=LaunchFailedError(str(error))
        )
    if _wait_until_healthy(
        host,
        health_checker,
        process,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        monotonic=monotonic,
        sleeper=sleeper,
    ):
        return ServiceLifecycleResult(
            status="started", pid=process.pid, command=launch_command
        )
    _terminate(host, process)
    host.remove_receipt(elfie_home)
    return ServiceLifecycleResult(
        status="failed",
        pid=process.pid,
        command=launch_command,
        error=LaunchFailedError(
            "Desktop did not pass the Web health check after startup"
        ),
    )


def stop_desktop_application(
    elfie_home: Path,
    *,
    host: DesktopHostPort,
    timeout_seconds: float = 10.0,
    poll_interval_seconds: float = 0.1,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> ServiceLifecycleResult:
    """Stop the Electron Desktop process referenced by the PID receipt."""
    pid = host.process_id(elfie_home)
    if pid is None:
        return ServiceLifecycleResult(status="already_stopped")
    try:
        host.terminate_pid(pid)
    except ProcessLookupError:
        host.remove_receipt(elfie_home)
        return ServiceLifecycleResult(status="already_stopped", pid=pid)
    deadline = monotonic() + timeout_seconds
    while host.exists(pid):
        if monotonic() >= deadline:
            return ServiceLifecycleResult(
                status="failed",
                pid=pid,
                error=StopTimeoutError(pid, timeout_seconds),
            )
        sleeper(poll_interval_seconds)
    host.remove_receipt(elfie_home)
    return ServiceLifecycleResult(status="stopped", pid=pid)


def desktop_process_id(elfie_home: Path, *, host: DesktopHostPort) -> Optional[int]:
    """Return the current Desktop supervisor PID, if live."""
    return host.process_id(elfie_home)


def _wait_until_healthy(
    host: DesktopHostPort,
    checker: Callable[[], bool],
    process: DesktopProcess,
    *,
    timeout_seconds: float,
    poll_interval_seconds: float,
    monotonic: Callable[[], float],
    sleeper: Callable[[float], None],
) -> bool:
    deadline = monotonic() + timeout_seconds
    while monotonic() < deadline:
        if process.poll() is not None:
            return False
        if checker():
            return True
        sleeper(poll_interval_seconds)
    return False


def _terminate(host: DesktopHostPort, process: DesktopProcess) -> None:
    if process.poll() is not None:
        return
    try:
        host.terminate(process)
        host.wait(process, timeout_seconds=2.0)
    except OSError:
        host.terminate(process, force=True)
