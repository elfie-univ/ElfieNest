"""User-visible service lifecycle commands."""

from __future__ import annotations

import os
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Optional, Sequence

from ai_runtime.storage.data_home import get_elfie_home
from app.features.administration.system_service import (
    default_port_statuses,
    service_port_statuses,
)
from app.orchestration.lifecycle import desktop as desktop_lifecycle
from app.orchestration.lifecycle.helpers import existing_service_command, read_pid
from app.orchestration.lifecycle.process import (
    PID_FILENAME,
    DefaultProcessInspector,
    ProcessInspector,
    http_port_from_command,
    service_ports_from_command,
    validate_service_ports,
)
from app.orchestration.lifecycle.service import start_service, stop_service
from app.orchestration.lifecycle.types import (
    LaunchFailedError,
    ServiceLifecycleResult,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
WEB_URL = "http://127.0.0.1:8000/"
WEB_HEALTH_URL = "http://127.0.0.1:8000/api/health"
BACKGROUND_START_TIMEOUT_SECONDS = 60.0


class ProgressIndicator:
    """Simple progress indicator with spinner animation."""
    
    def __init__(self, message: str = "Starting"):
        self.message = message
        self.running = False
        self.thread = None
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    
    def _spin(self):
        idx = 0
        while self.running:
            spinner = self.spinner_chars[idx % len(self.spinner_chars)]
            print(f"\r  {spinner} {self.message}...", end="", flush=True)
            time.sleep(0.1)
            idx += 1
    
    def start(self):
        """Start the spinner animation."""
        self.running = True
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()
    
    def stop(self, success: bool = True):
        """Stop the spinner and show result."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.2)
        print(f"\r  {'✅' if success else '❌'} {self.message}{' ✓' if success else ' ✗'}    ", flush=True)


def default_service_command(extra_args: Sequence[str] = ()) -> tuple[str, ...]:
    """Build the background command without the foreground-only force flag."""
    filtered = tuple(argument for argument in extra_args if argument != "--force")
    packaged_core = os.environ.get("ELFIENEST_CORE_BIN")
    if packaged_core:
        return (packaged_core, *filtered)
    return (
        sys.executable,
        str((PROJECT_ROOT / "scripts" / "serve.py").resolve()),
        *filtered,
    )


def start_background_service(
    command: Optional[Sequence[str]] = None,
) -> ServiceLifecycleResult:
    """Start the service once; a verified running process is left untouched."""
    progress = ProgressIndicator("Starting service")
    progress.start()
    
    launch_command = (
        tuple(command) if command is not None else default_service_command(("--lan",))
    )
    try:
        http_port = _validated_http_port(launch_command)
    except ValueError as error:
        progress.stop(success=False)
        result = ServiceLifecycleResult(
            status="failed", error=LaunchFailedError(f"Invalid service port: {error}")
        )
        _print_start_result(result)
        return result
    
    result = start_service(
        get_elfie_home(),
        PROJECT_ROOT,
        command=launch_command,
        health_checker=lambda: _web_is_healthy(http_port),
        timeout_seconds=BACKGROUND_START_TIMEOUT_SECONDS,
    )
    progress.stop(success=result.status in {"started", "already_running"})
    _print_start_result(result)
    return result


def stop_background_service() -> ServiceLifecycleResult:
    """Stop only the current project's verified service process."""
    result = stop_service(get_elfie_home(), PROJECT_ROOT)
    if result.status == "stopped":
        print("  ✅ Service stopped")
    elif result.status == "already_stopped":
        print("  ⭕ Service not running")
    else:
        print(f"  ❌ Failed to stop service: {result.error}")
    return result


def restart_background_service() -> ServiceLifecycleResult:
    """Stop the current process and start it again with its existing arguments."""
    progress = ProgressIndicator("Restarting service")
    progress.start()
    
    stopped = stop_service(get_elfie_home(), PROJECT_ROOT)
    if stopped.status == "failed":
        progress.stop(success=False)
        print(f"  ❌ Cannot restart service: {stopped.error}")
        return stopped
    command = stopped.command or default_service_command(("--lan",))
    try:
        http_port = _validated_http_port(command)
    except ValueError as error:
        progress.stop(success=False)
        result = ServiceLifecycleResult(
            status="failed", error=LaunchFailedError(f"Invalid service port: {error}")
        )
        print(f"  ❌ Service restart failed: {result.error}")
        return result
    result = start_service(
        get_elfie_home(),
        PROJECT_ROOT,
        command=tuple(argument for argument in command if argument != "--force"),
        health_checker=lambda: _web_is_healthy(http_port),
        timeout_seconds=BACKGROUND_START_TIMEOUT_SECONDS,
    )
    progress.stop(success=result.status in {"started", "already_running"})
    if result.status in {"started", "already_running"}:
        print("  ✅ Service restarted")
    else:
        print(f"  ❌ Service restart failed: {result.error}")
    return result


def show_service_status() -> None:
    """Print lifecycle state without duplicating usage/session statistics."""
    print("  📊 Service Status")
    print("  " + "=" * 45)
    print()
    inspector = DefaultProcessInspector()
    elfie_home = get_elfie_home()
    running = existing_service_command(elfie_home, PROJECT_ROOT, inspector)
    if running is None:
        port_statuses = default_port_statuses()
        external = _external_recorded_service(elfie_home, inspector)
        if external is not None:
            pid, cwd, _ = external
            print(f"  ⚠️  Registered PID {pid} from another ElfieNest checkout: {cwd}")
        elif any(port_status.running for port_status in port_statuses):
            print("  ⚠️  Default service ports occupied by external process, no verified service for current project.")
    else:
        _, command = running
        ports = service_ports_from_command(command)
        port_statuses = service_port_statuses(ports[0], ports[2], ports[1])
    for port_status in port_statuses:
        is_current_project = running is not None
        state = (
            "running"
            if is_current_project and port_status.running
            else "occupied by external process"
            if port_status.running
            else "not running"
        )
        icon = (
            "✅"
            if is_current_project and port_status.running
            else "⚠️"
            if port_status.running
            else "⭕"
        )
        print(f"  {icon} {port_status.name}: {state} (port {port_status.port})")
    print()


def open_web_console() -> ServiceLifecycleResult:
    """Ensure a healthy service and open the Web management console."""
    running = existing_service_command(
        get_elfie_home(), PROJECT_ROOT, DefaultProcessInspector()
    )
    if running is not None:
        _, running_command = running
        port = http_port_from_command(running_command)
        if not _web_is_healthy(port):
            result = ServiceLifecycleResult(
                status="failed",
                error=LaunchFailedError(f"Registered service but Web port {port} failed health check"),
            )
            print(f"  ❌ Cannot open Web console: {result.error}")
            return result
    else:
        if _web_is_healthy(8000):
            webbrowser.open(WEB_URL)
            print(f"  🌐 Opened running Web console: {WEB_URL}")
            print("  ⚠️  Service not verified by current project PID receipt; start/restart won't take over.")
            return ServiceLifecycleResult(status="already_running")
        if any(port_status.running for port_status in default_port_statuses()):
            result = ServiceLifecycleResult(
                status="failed",
                error=LaunchFailedError(
                    "Default service ports occupied by external process and Web health check failed; "
                    "manage it from the owning checkout, or start current project with custom ports"
                ),
            )
            print(f"  ❌ Cannot open Web console: {result.error}")
            return result
        result = start_background_service()
        if result.status not in {"started", "already_running"}:
            return result
        port = http_port_from_command(
            result.command or default_service_command(("--lan",))
        )
        if not _web_is_healthy(port):
            result = ServiceLifecycleResult(
                status="failed",
                error=LaunchFailedError(f"Service started but Web port {port} failed health check"),
            )
            print(f"  ❌ Cannot open Web console: {result.error}")
            return result
    web_url = f"http://127.0.0.1:{port}/"
    webbrowser.open(web_url)
    print(f"  🌐 Opened Web console: {web_url}")
    return ServiceLifecycleResult(status="already_running")


def start_desktop_application() -> ServiceLifecycleResult:
    """Explicitly start the packaged Electron Desktop supervisor."""
    result = desktop_lifecycle.start_desktop_application(
        get_elfie_home(), PROJECT_ROOT, health_checker=_web_is_healthy
    )
    if result.status in {"started", "already_running"}:
        print(f"  ✅ Desktop started (PID {result.pid})")
    else:
        print(f"  ❌ Desktop failed to start: {result.error}")
    return result


def _web_is_healthy(port: int = 8000) -> bool:
    health_url = f"http://127.0.0.1:{port}/api/health"
    try:
        with urllib.request.urlopen(health_url, timeout=2.0) as response:
            return response.status == 200
    except (OSError, TimeoutError, urllib.error.URLError):
        return False


def _external_recorded_service(
    elfie_home: Path,
    inspector: ProcessInspector,
) -> tuple[int, Path, tuple[str, ...]] | None:
    """Return a live recorded service that belongs to another checkout."""
    pid_path = elfie_home / PID_FILENAME
    if not pid_path.exists():
        return None
    try:
        pid_result = read_pid(pid_path)
    except OSError:
        return None
    if not isinstance(pid_result, int) or not inspector.exists(pid_result):
        return None
    try:
        cwd = inspector.cwd(pid_result).resolve()
        command = inspector.command(pid_result)
    except (OSError, RuntimeError, ValueError):
        return None
    if cwd == PROJECT_ROOT.resolve():
        return None
    return pid_result, cwd, tuple(command)


def _validated_http_port(command: Sequence[str]) -> int:
    """Parse and validate HTTP/WS ports before spawning a service process."""
    ports = service_ports_from_command(command)
    error = validate_service_ports(ports[0], ports[2], ports[1])
    if error:
        raise ValueError(error)
    return ports[0]


def _print_start_result(result: ServiceLifecycleResult) -> None:
    if result.status == "started":
        print(f"  ✅ Service started (PID {result.pid})")
    elif result.status == "already_running":
        print(f"  ⭕ Service already running (PID {result.pid})")
    else:
        print(f"  ❌ Service failed to start: {result.error}")
