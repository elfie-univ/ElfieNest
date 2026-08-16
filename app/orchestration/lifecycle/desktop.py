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
    background: bool = False,
) -> ServiceLifecycleResult:
    """Start a complete service supervised by Electron.

    ``background`` starts the same Controller and tray without opening the
    Viewer. The Controller still owns the Runtime; only its presentation is
    suppressed.
    """
    existing_pid = host.process_id(elfie_home)
    if existing_pid is not None:
        if health_checker():
            return ServiceLifecycleResult(status="already_running", pid=existing_pid)
        executable = host.find_executable(project_root)
        if executable is None:
            return ServiceLifecycleResult(
                status="failed",
                pid=existing_pid,
                error=LaunchFailedError(
                    "ElfieNest Controller is running but its packaged executable is unavailable"
                ),
            )
        try:
            activation = host.launch((str(executable), "--background"), project_root)
        except OSError as error:
            return ServiceLifecycleResult(
                status="failed", pid=existing_pid, error=LaunchFailedError(str(error))
            )
        if _wait_for_health(
            health_checker,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            monotonic=monotonic,
            sleeper=sleeper,
        ):
            return ServiceLifecycleResult(status="already_running", pid=existing_pid)
        _terminate(host, activation)
        return ServiceLifecycleResult(
            status="failed",
            pid=existing_pid,
            error=LaunchFailedError(
                "Existing ElfieNest Controller did not restore the Server"
            ),
        )
    executable = host.find_executable(project_root)
    launch_command = (
        tuple(command)
        if command is not None
        else (
            (str(executable), "--background")
            if executable and background
            else ((str(executable),) if executable else ())
        )
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


def _wait_for_health(
    checker: Callable[[], bool],
    *,
    timeout_seconds: float,
    poll_interval_seconds: float,
    monotonic: Callable[[], float],
    sleeper: Callable[[float], None],
) -> bool:
    """Wait for an existing Controller to restore its Server.

    The activation helper process is expected to exit after forwarding the
    request to the single Controller, so its own PID is not part of readiness.
    """
    deadline = monotonic() + timeout_seconds
    while monotonic() < deadline:
        if checker():
            return True
        sleeper(poll_interval_seconds)
    return checker()


def _terminate(host: DesktopHostPort, process: DesktopProcess) -> None:
    if process.poll() is not None:
        return
    try:
        host.terminate(process)
        host.wait(process, timeout_seconds=2.0)
    except OSError:
        host.terminate(process, force=True)
