"""Lifecycle management for packaged ElfieNest Desktop."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional, Sequence

from app.orchestration.lifecycle.types import (
    LaunchFailedError,
    ServiceLifecycleResult,
    StopTimeoutError,
)

PID_NAME = "desktop.pid"


def find_desktop_executable(project_root: Path) -> Optional[Path]:
    """Find packaged desktop supervisor; returns None if not in source environment."""
    configured = os.environ.get("ELFIENEST_DESKTOP_BIN", "").strip()
    candidates = [Path(configured).expanduser()] if configured else []
    candidates.extend(
        [
            project_root / ".elfienest" / "runtime" / "ElfieNestDesktop",
            project_root / "dist" / "ElfieNestDesktop",
            project_root
            / "dist"
            / "ElfieNest.app"
            / "Contents"
            / "MacOS"
            / "ElfieNest",
            project_root / "dist" / "win-unpacked" / "ElfieNest.exe",
            project_root / "dist" / "linux-unpacked" / "elfienest",
        ]
    )
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return resolved
    return None


def start_desktop_application(
    elfie_home: Path,
    project_root: Path,
    *,
    command: Optional[Sequence[str]] = None,
    health_checker: Callable[[], bool],
) -> ServiceLifecycleResult:
    """Start a complete service supervised by Electron."""
    pid_path = _pid_path(elfie_home)
    existing_pid = _read_live_pid(pid_path)
    if existing_pid is not None:
        return ServiceLifecycleResult(status="already_running", pid=existing_pid)
    executable = find_desktop_executable(project_root)
    launch_command = (
        tuple(command)
        if command is not None
        else ((str(executable),) if executable else ())
    )
    if not launch_command:
        return ServiceLifecycleResult(
            status="failed",
            error=LaunchFailedError("ElfieNest Desktop not found; please build desktop app first"),
        )
    try:
        process = subprocess.Popen(
            list(launch_command),
            cwd=str(project_root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as error:
        return ServiceLifecycleResult(
            status="failed", error=LaunchFailedError(str(error))
        )
    _write_pid(pid_path, process.pid)
    if _wait_until_healthy(health_checker, process):
        return ServiceLifecycleResult(
            status="started", pid=process.pid, command=launch_command
        )
    _terminate(process)
    pid_path.unlink(missing_ok=True)
    return ServiceLifecycleResult(
        status="failed",
        pid=process.pid,
        command=launch_command,
        error=LaunchFailedError("Desktop did not pass the Web health check after startup"),
    )


def stop_desktop_application(elfie_home: Path) -> ServiceLifecycleResult:
    """Stop the Electron Desktop process referenced by the PID receipt."""
    pid_path = _pid_path(elfie_home, create=False)
    pid = _read_pid(pid_path)
    if pid is None:
        return ServiceLifecycleResult(status="already_stopped")
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pid_path.unlink(missing_ok=True)
        return ServiceLifecycleResult(status="already_stopped", pid=pid)
    deadline = time.monotonic() + 10.0
    while _process_exists(pid):
        if time.monotonic() >= deadline:
            return ServiceLifecycleResult(
                status="failed", pid=pid, error=StopTimeoutError(pid, 10.0)
            )
        time.sleep(0.1)
    pid_path.unlink(missing_ok=True)
    return ServiceLifecycleResult(status="stopped", pid=pid)


def desktop_process_id(elfie_home: Path) -> Optional[int]:
    """Return the current Desktop supervisor PID, or None when absent or exited."""
    return _read_live_pid(_pid_path(elfie_home, create=False))


def _pid_path(elfie_home: Path, *, create: bool = True) -> Path:
    runtime_dir = elfie_home / "runtime"
    if create:
        runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir / PID_NAME


def _read_pid(pid_path: Path) -> Optional[int]:
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, OSError, ValueError):
        return None
    return pid if _process_exists(pid) else None


def _read_live_pid(pid_path: Path) -> Optional[int]:
    pid = _read_pid(pid_path)
    if pid is None:
        pid_path.unlink(missing_ok=True)
    return pid


def _write_pid(pid_path: Path, pid: int) -> None:
    pid_path.write_text(str(pid), encoding="utf-8")
    if os.name != "nt":
        pid_path.chmod(0o600)


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_until_healthy(checker: Callable[[], bool], process: subprocess.Popen) -> bool:
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        if checker():
            return True
        time.sleep(0.2)
    return False


def _terminate(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=2.0)
    except (OSError, subprocess.TimeoutExpired):
        process.kill()
