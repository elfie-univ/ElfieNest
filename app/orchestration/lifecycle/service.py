"""Safe lifecycle management for the local ElfieNest service."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

from app.orchestration.lifecycle.helpers import (
    default_launcher,
    existing_service_command,
    read_pid,
)
from app.orchestration.lifecycle.process import (
    DEFAULT_SERVICE_PORTS,
    PID_FILENAME,
    DefaultProcessInspector,
    ProcessInspector,
    any_service_port_in_use,
    command_runs_service,
    register_service_process,
    remove_service_process,
    restart_command_from_process,
    service_ports_from_command,
)
from app.orchestration.lifecycle.recovery_lock import (
    RecoveryInProgressError,
    acquire_service_start_lease,
)
from app.orchestration.lifecycle.start_cleanup import cleanup_failed_start
from app.orchestration.lifecycle.types import (
    HealthCheckFailedError,
    InvalidPidFileError,
    LaunchFailedError,
    ProcessIdentityMismatchError,
    ProcessInspectionError,
    ServiceLifecycleResult,
    ServicePortsActiveError,
    SignalProcessError,
    StopTimeoutError,
)

_default_launcher = default_launcher
_read_pid = read_pid


def stop_service(
    elfie_home: Path,
    project_root: Path,
    *,
    inspector: Optional[ProcessInspector] = None,
    signaler: Callable[[int, int], None] = os.kill,
    timeout_seconds: float = 10.0,
    poll_interval_seconds: float = 0.1,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    service_ports_in_use: Callable[[Sequence[int]], bool] = any_service_port_in_use,
) -> ServiceLifecycleResult:
    """Stop the service only when the PID identity exactly matches this project."""
    pid_path = elfie_home / PID_FILENAME
    if not pid_path.exists():
        if service_ports_in_use(DEFAULT_SERVICE_PORTS):
            return ServiceLifecycleResult(
                status="failed",
                error=ServicePortsActiveError("Missing verifiable PID receipt"),
            )
        return ServiceLifecycleResult(status="already_stopped")

    try:
        pid_result = _read_pid(pid_path)
    except OSError as error:
        return ServiceLifecycleResult(
            status="failed", error=InvalidPidFileError(pid_path, str(error))
        )
    if isinstance(pid_result, InvalidPidFileError):
        return ServiceLifecycleResult(status="failed", error=pid_result)
    pid = pid_result
    process_inspector = inspector or DefaultProcessInspector()

    try:
        if not process_inspector.exists(pid):
            if service_ports_in_use(DEFAULT_SERVICE_PORTS):
                return ServiceLifecycleResult(
                    status="failed",
                    pid=pid,
                    error=ServicePortsActiveError("PID is no longer valid"),
                )
            remove_service_process(elfie_home, pid)
            return ServiceLifecycleResult(status="already_stopped", pid=pid)
        actual_cwd = process_inspector.cwd(pid).resolve()
        actual_command = process_inspector.command(pid)
    except ProcessInspectionError as error:
        return ServiceLifecycleResult(status="failed", pid=pid, error=error)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        inspection_error = ProcessInspectionError(pid, str(error))
        return ServiceLifecycleResult(status="failed", pid=pid, error=inspection_error)

    expected_cwd = project_root.resolve()
    expected_script = (expected_cwd / "scripts" / "serve.py").resolve()
    if actual_cwd != expected_cwd or not command_runs_service(
        actual_command, actual_cwd, expected_script
    ):
        mismatch = ProcessIdentityMismatchError(
            pid, expected_cwd, actual_cwd, expected_script, actual_command
        )
        return ServiceLifecycleResult(status="failed", pid=pid, error=mismatch)

    try:
        if not process_inspector.exists(pid):
            remove_service_process(elfie_home, pid)
            return ServiceLifecycleResult(status="already_stopped", pid=pid)
        confirmed_cwd = process_inspector.cwd(pid).resolve()
        confirmed_command = process_inspector.command(pid)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        inspection_error = ProcessInspectionError(pid, str(error))
        return ServiceLifecycleResult(status="failed", pid=pid, error=inspection_error)
    if confirmed_cwd != actual_cwd or confirmed_command != actual_command:
        mismatch = ProcessIdentityMismatchError(
            pid, expected_cwd, confirmed_cwd, expected_script, confirmed_command
        )
        return ServiceLifecycleResult(status="failed", pid=pid, error=mismatch)

    try:
        signaler(pid, signal.SIGTERM)
    except OSError as error:
        signal_error = SignalProcessError(pid, str(error))
        return ServiceLifecycleResult(status="failed", pid=pid, error=signal_error)

    deadline = monotonic() + timeout_seconds
    while process_inspector.exists(pid):
        if monotonic() >= deadline:
            timeout_error = StopTimeoutError(pid, timeout_seconds)
            return ServiceLifecycleResult(status="failed", pid=pid, error=timeout_error)
        sleeper(poll_interval_seconds)
    try:
        target_ports = service_ports_from_command(actual_command)
    except ValueError as error:
        return ServiceLifecycleResult(
            status="failed",
            pid=pid,
            error=ProcessInspectionError(
                pid, f"Invalid service port arguments: {error}"
            ),
        )
    if service_ports_in_use(target_ports):
        return ServiceLifecycleResult(
            status="failed",
            pid=pid,
            error=ServicePortsActiveError(
                "Service ports are still occupied after the target process exited"
            ),
        )
    remove_service_process(elfie_home, pid)
    return ServiceLifecycleResult(
        status="stopped",
        pid=pid,
        command=restart_command_from_process(actual_command),
    )


def start_service(
    elfie_home: Path,
    project_root: Path,
    *,
    health_checker: Callable[[], bool],
    command: Optional[Sequence[str]] = None,
    launcher: Optional[Callable[[Sequence[str], Path], int]] = None,
    inspector: Optional[ProcessInspector] = None,
    signaler: Callable[[int, int], None] = os.kill,
    timeout_seconds: float = 10.0,
    poll_interval_seconds: float = 0.1,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    service_ports_in_use: Optional[Callable[[Sequence[int]], bool]] = None,
    child_environment: Optional[Mapping[str, str]] = None,
) -> ServiceLifecycleResult:
    """Start the service; terminate it and remove the PID file when health fails."""
    resolved_root = project_root.resolve()
    launch_command = (
        tuple(command)
        if command is not None
        else (
            sys.executable,
            str((resolved_root / "scripts" / "serve.py").resolve()),
            "--fallback",
        )
    )
    process_launcher = launcher or (
        lambda requested_command, cwd: default_launcher(
            requested_command,
            cwd,
            child_environment=child_environment,
        )
    )
    process_inspector = inspector or DefaultProcessInspector()
    try:
        startup_lease = acquire_service_start_lease(elfie_home)
    except (OSError, RecoveryInProgressError) as error:
        return ServiceLifecycleResult(
            status="failed",
            error=LaunchFailedError(f"Service startup blocked: {error}"),
        )
    lease_released = False
    try:
        existing = existing_service_command(
            elfie_home, resolved_root, process_inspector
        )
        if existing is not None:
            existing_pid, existing_command = existing
            requested_ports = service_ports_from_command(launch_command)
            existing_ports = service_ports_from_command(existing_command)
            if requested_ports != existing_ports:
                return ServiceLifecycleResult(
                    status="failed",
                    pid=existing_pid,
                    error=LaunchFailedError(
                        "An existing service is using different ports; run restart or stop before changing ports"
                    ),
                )
            try:
                existing_healthy = health_checker()
            except (OSError, RuntimeError, ValueError):
                existing_healthy = False
            if not existing_healthy:
                return ServiceLifecycleResult(
                    status="failed",
                    pid=existing_pid,
                    command=existing_command,
                    error=HealthCheckFailedError(existing_pid, 0.0),
                )
            return ServiceLifecycleResult(
                status="already_running", pid=existing_pid, command=existing_command
            )

        port_checker = (
            any_service_port_in_use if launcher is None else service_ports_in_use
        )
        if port_checker is not None:
            requested_ports = service_ports_from_command(launch_command)
            if port_checker(requested_ports):
                return ServiceLifecycleResult(
                    status="failed",
                    error=ServicePortsActiveError(
                        "Target ports are already occupied by another process"
                    ),
                )

        pid = process_launcher(launch_command, resolved_root)
        if pid <= 0:
            return ServiceLifecycleResult(
                status="failed",
                error=LaunchFailedError(f"Launcher returned invalid PID {pid}"),
            )

        pid_path = elfie_home / PID_FILENAME
        try:
            register_service_process(elfie_home, pid)
        except OSError as error:
            launch_error = LaunchFailedError(f"Unable to register PID {pid}: {error}")
            return cleanup_failed_start(
                pid=pid,
                pid_path=pid_path,
                original_error=launch_error,
                inspector=process_inspector,
                signaler=signaler,
                expected_cwd=resolved_root,
                expected_script=(resolved_root / "scripts" / "serve.py").resolve(),
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
                monotonic=monotonic,
                sleeper=sleeper,
            )

        startup_lease.release()
        lease_released = True
        deadline = monotonic() + timeout_seconds
        while True:
            if not process_inspector.exists(pid):
                remove_service_process(elfie_home, pid)
                return ServiceLifecycleResult(
                    status="failed",
                    pid=pid,
                    error=LaunchFailedError(
                        "Service exited before passing the health check"
                    ),
                    command=launch_command,
                )
            try:
                healthy = health_checker()
            except (OSError, RuntimeError, ValueError):
                return cleanup_failed_start(
                    pid=pid,
                    pid_path=pid_path,
                    original_error=HealthCheckFailedError(pid, timeout_seconds),
                    inspector=process_inspector,
                    signaler=signaler,
                    expected_cwd=resolved_root,
                    expected_script=(resolved_root / "scripts" / "serve.py").resolve(),
                    timeout_seconds=timeout_seconds,
                    poll_interval_seconds=poll_interval_seconds,
                    monotonic=monotonic,
                    sleeper=sleeper,
                )
            if healthy:
                return ServiceLifecycleResult(
                    status="started", pid=pid, command=launch_command
                )
            if monotonic() >= deadline:
                return cleanup_failed_start(
                    pid=pid,
                    pid_path=pid_path,
                    original_error=HealthCheckFailedError(pid, timeout_seconds),
                    inspector=process_inspector,
                    signaler=signaler,
                    expected_cwd=resolved_root,
                    expected_script=(resolved_root / "scripts" / "serve.py").resolve(),
                    timeout_seconds=timeout_seconds,
                    poll_interval_seconds=poll_interval_seconds,
                    monotonic=monotonic,
                    sleeper=sleeper,
                )
            sleeper(poll_interval_seconds)
    except (OSError, ValueError) as error:
        return ServiceLifecycleResult(
            status="failed", error=LaunchFailedError(str(error))
        )
    finally:
        if not lease_released:
            startup_lease.release()
