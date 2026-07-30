"""User-visible service lifecycle commands."""

from __future__ import annotations

import json
import os
import secrets
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Callable, Final, Optional, Sequence

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.providers.ollama import OllamaManager, OllamaNotReadyError
from ai_runtime.storage.data_home import (
    DataHomeSelectionError,
    get_elfie_home,
    resolve_elfie_home,
)
from app.features.administration.system_service import (
    default_port_statuses,
    service_port_statuses,
)
from app.orchestration.lifecycle import desktop as desktop_lifecycle
from app.orchestration.lifecycle.authority import (
    AuthorityLifecycleConfig,
    authority_lifecycle,
)
from app.orchestration.lifecycle.helpers import existing_service_command, read_pid
from app.orchestration.lifecycle.process import (
    DEFAULT_HTTP_PORT,
    PID_FILENAME,
    DefaultProcessInspector,
    ProcessInspector,
    http_port_from_command,
    service_ports_from_command,
    validate_service_ports,
)
from app.orchestration.lifecycle.runtime_health import (
    ComponentHealth,
    RuntimeComponent,
    RuntimeHealth,
    RuntimeHealthState,
)
from app.orchestration.lifecycle.runtime_supervisor import RuntimeSupervisor
from app.orchestration.lifecycle.service import start_service, stop_service
from app.orchestration.lifecycle.types import (
    LaunchFailedError,
    ServiceLifecycleResult,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
WEB_URL = "http://127.0.0.1:8000/"
WEB_HEALTH_URL = "http://127.0.0.1:8000/api/health"
BACKGROUND_START_TIMEOUT_SECONDS = 60.0
AUTHORITY_START_TIMEOUT_SECONDS = 120.0
SELECTED_DATA_HOME_RECEIPT: Final = "selected-data-home"


def _supervisor_for(
    command: Sequence[str],
    http_port: int,
    *,
    use_remembered_home: bool = False,
) -> RuntimeSupervisor:
    """Build the one Runtime Supervisor used by source and installed CLI commands."""
    launch_command = tuple(command)
    selected_home = _data_home_for_command(
        launch_command,
        use_remembered_home=use_remembered_home,
    )
    _, godot_ws_port, _ = service_ports_from_command(launch_command)
    generation_nonce = secrets.token_urlsafe(32)
    start_authority, stop_authority = authority_lifecycle(
        AuthorityLifecycleConfig(
            project_root=PROJECT_ROOT,
            http_port=http_port,
            ws_port=godot_ws_port,
            nonce=generation_nonce,
        )
    )

    def start_core(healthy: Callable[[], bool]) -> ServiceLifecycleResult:
        return start_service(
            selected_home,
            PROJECT_ROOT,
            command=launch_command,
            health_checker=healthy,
            timeout_seconds=BACKGROUND_START_TIMEOUT_SECONDS,
            child_environment={
                "ELFIE_HOME": str(selected_home),
                "ELFIENEST_GODOT_NONCE": generation_nonce,
            },
        )

    return RuntimeSupervisor(
        elfie_home=selected_home,
        project_root=PROJECT_ROOT,
        health_probe=lambda: _full_runtime_health(http_port),
        start_core=start_core,
        stop_core=lambda: stop_service(selected_home, PROJECT_ROOT),
        prepare_optional_component=_start_configured_public_ollama,
        owns_pid_record=lambda: (selected_home / PID_FILENAME).is_file(),
        start_authority=start_authority,
        stop_authority=stop_authority,
        authority_timeout_seconds=AUTHORITY_START_TIMEOUT_SECONDS,
    )


def _full_runtime_health(port: int) -> RuntimeHealth:
    """Probe every Runtime component; an HTTP 200 alone is never ready."""
    failed = RuntimeHealthState.FAILED
    core = failed
    gateway = failed
    authority = failed
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/health", timeout=2.0
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if response.status == 200 and isinstance(payload, dict):
            engine_ready = payload.get("engine_ready") is True
            core = RuntimeHealthState.READY if engine_ready else failed
            gateway = RuntimeHealthState.READY if engine_ready else failed
            authority = (
                RuntimeHealthState.READY
                if payload.get("godot_runtime_ready") is True
                else failed
            )
    except (OSError, TimeoutError, ValueError, urllib.error.URLError):
        pass
    ollama = (
        RuntimeHealthState.READY
        if _configured_ollama_is_ready()
        else RuntimeHealthState.FAILED
    )
    return RuntimeHealth(
        state=RuntimeHealthState.STARTING,
        generation=0,
        owner_lease=None,
        components=(
            ComponentHealth(RuntimeComponent.CORE, core),
            ComponentHealth(RuntimeComponent.GATEWAY, gateway),
            ComponentHealth(RuntimeComponent.GODOT_AUTHORITY, authority),
            ComponentHealth(RuntimeComponent.OLLAMA, ollama),
        ),
    )


def _configured_ollama_is_ready() -> bool:
    """Probe Ollama without adopting or stopping a public installation."""
    return OllamaManager(
        LLMRuntimeConfig(ollama_host="http://localhost:11434")
    ).check_health()


def _start_configured_public_ollama() -> None:
    """Only request startup through Ollama's recorded public-installation binding."""
    manager = OllamaManager(LLMRuntimeConfig(ollama_host="http://localhost:11434"))
    try:
        manager.ensure_service_started()
    except OllamaNotReadyError:
        return


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
        print(
            f"\r  {'✅' if success else '❌'} {self.message}{' ✓' if success else ' ✗'}    ",
            flush=True,
        )


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


def _data_home_for_command(
    command: Sequence[str],
    *,
    use_remembered_home: bool = False,
) -> Path:
    """从服务命令与已记录生命周期选择中解析数据根。"""
    explicit_home = _option_value(command, "--data-home")
    if explicit_home is not None:
        return resolve_elfie_home(
            explicit_home,
            invoking_cwd=PROJECT_ROOT,
            runtime_mode=os.environ.get("ELFIENEST_RUNTIME_MODE", "development"),
            source_root=PROJECT_ROOT,
        )
    if use_remembered_home:
        remembered_home = _remembered_lifecycle_data_home()
        if remembered_home is not None:
            return remembered_home
    return resolve_elfie_home(
        None,
        invoking_cwd=PROJECT_ROOT,
        runtime_mode=os.environ.get("ELFIENEST_RUNTIME_MODE", "development"),
        source_root=PROJECT_ROOT,
    )


def _option_value(command: Sequence[str], option: str) -> Optional[str]:
    for index, argument in enumerate(command):
        if argument == option:
            value_index = index + 1
            if value_index >= len(command):
                raise DataHomeSelectionError(f"{option} requires a value")
            return command[value_index]
        prefix = f"{option}="
        if argument.startswith(prefix):
            return argument[len(prefix) :]
    return None


def _remember_lifecycle_data_home(selected_home: Path) -> None:
    """原子记录当前 checkout 最近一次成功选择的数据根。"""
    receipt_home = _lifecycle_receipt_home()
    receipt_path = receipt_home / "runtime" / SELECTED_DATA_HOME_RECEIPT
    receipt_home.mkdir(mode=0o700, parents=True, exist_ok=True)
    receipt_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(receipt_home, 0o700)
        os.chmod(receipt_path.parent, 0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{SELECTED_DATA_HOME_RECEIPT}.",
        dir=str(receipt_path.parent),
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as receipt:
            receipt.write(str(selected_home.resolve(strict=False)))
            receipt.write("\n")
        temporary_path.replace(receipt_path)
    except OSError:
        temporary_path.unlink(missing_ok=True)
        raise


def _remembered_lifecycle_data_home() -> Optional[Path]:
    """读取当前 checkout 最近一次有效的数据根选择。"""
    try:
        selected_home = (
            _lifecycle_data_home_receipt_path().read_text(encoding="utf-8").strip()
        )
    except OSError:
        return None
    if not selected_home:
        return None
    try:
        return resolve_elfie_home(
            selected_home,
            invoking_cwd=PROJECT_ROOT,
            runtime_mode=os.environ.get("ELFIENEST_RUNTIME_MODE", "development"),
            source_root=PROJECT_ROOT,
        )
    except DataHomeSelectionError:
        return None


def _lifecycle_data_home_receipt_path() -> Path:
    return _lifecycle_receipt_home() / "runtime" / SELECTED_DATA_HOME_RECEIPT


def _lifecycle_receipt_home() -> Path:
    return resolve_elfie_home(
        None,
        invoking_cwd=PROJECT_ROOT,
        runtime_mode=os.environ.get("ELFIENEST_RUNTIME_MODE", "development"),
        source_root=PROJECT_ROOT,
        env={},
    )


def start_background_service(
    command: Optional[Sequence[str]] = None,
    *,
    owner_id: str = "cli",
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
    result = _supervisor_for(launch_command, http_port).start(owner_id=owner_id)
    if result.status in {"started", "already_running"}:
        try:
            _remember_lifecycle_data_home(_data_home_for_command(launch_command))
        except OSError as error:
            result = ServiceLifecycleResult(
                status="failed",
                pid=result.pid,
                command=result.command,
                error=LaunchFailedError(f"Cannot record selected data home: {error}"),
            )
    progress.stop(success=result.status in {"started", "already_running"})
    _print_start_result(result)
    return result


def stop_background_service(owner_id: str = "cli") -> ServiceLifecycleResult:
    """Stop only the current project's verified service process."""
    supervisor = _supervisor_for(
        default_service_command(),
        DEFAULT_HTTP_PORT,
        use_remembered_home=True,
    )
    if owner_id != "cli":
        health = supervisor.status()
        if health.owner_lease is not None and health.owner_lease.owner_id != owner_id:
            result = ServiceLifecycleResult(
                status="failed",
                error=LaunchFailedError(
                    "Runtime owner lease does not allow this client to stop the service"
                ),
            )
            print(f"  ❌ Failed to stop service: {result.error}")
            return result
    result = supervisor.stop()
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

    stopped = _supervisor_for(
        default_service_command(),
        DEFAULT_HTTP_PORT,
        use_remembered_home=True,
    ).stop()
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
    launch_command = tuple(argument for argument in command if argument != "--force")
    result = _supervisor_for(launch_command, http_port).start(owner_id="cli")
    progress.stop(success=result.status in {"started", "already_running"})
    if result.status in {"started", "already_running"}:
        print("  ✅ Service restarted")
    else:
        print(f"  ❌ Service restart failed: {result.error}")
    return result


def show_service_status(*, json_output: bool = False) -> None:
    """Print lifecycle state without duplicating usage/session statistics."""
    inspector = DefaultProcessInspector()
    elfie_home = _data_home_for_command(
        default_service_command(),
        use_remembered_home=True,
    )
    running = existing_service_command(elfie_home, PROJECT_ROOT, inspector)
    status_command = running[1] if running is not None else default_service_command()
    status_port = http_port_from_command(status_command)
    health = _supervisor_for(
        status_command,
        status_port,
        use_remembered_home=running is None,
    ).status()
    if json_output:
        print(
            json.dumps(
                {
                    "state": health.state.value,
                    "generation": health.generation,
                    "owner_lease": (
                        {
                            "owner_id": health.owner_lease.owner_id,
                            "generation": health.owner_lease.generation,
                        }
                        if health.owner_lease is not None
                        else None
                    ),
                    "components": [
                        {
                            "name": component.component.value,
                            "state": component.state.value,
                            "detail": component.detail,
                            "pid": component.pid,
                        }
                        for component in health.components
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return
    print("  📊 Service Status")
    print("  " + "=" * 45)
    print()
    if running is None:
        port_statuses = default_port_statuses()
        external = _external_recorded_service(elfie_home, inspector)
        if external is not None:
            pid, cwd, _ = external
            print(f"  ⚠️  Registered PID {pid} from another ElfieNest checkout: {cwd}")
        elif any(port_status.running for port_status in port_statuses):
            print(
                "  ⚠️  Default service ports occupied by external process, no verified service for current project."
            )
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
    if health.components:
        print()
        print(f"  Runtime: {health.state.value} (generation {health.generation})")
        for component in health.components:
            print(f"  - {component.component.value}: {component.state.value}")
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
                error=LaunchFailedError(
                    f"Registered service but Web port {port} failed health check"
                ),
            )
            print(f"  ❌ Cannot open Web console: {result.error}")
            return result
    else:
        if _web_is_healthy(8000):
            webbrowser.open(WEB_URL)
            print(f"  🌐 Opened running Web console: {WEB_URL}")
            print(
                "  ⚠️  Service not verified by current project PID receipt; start/restart won't take over."
            )
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
                error=LaunchFailedError(
                    f"Service started but Web port {port} failed health check"
                ),
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
