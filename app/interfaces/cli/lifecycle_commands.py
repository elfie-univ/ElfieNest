"""用户可见的服务生命周期命令。"""

from __future__ import annotations

import json
import os
import secrets
import sys
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Callable, Optional, Sequence

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.providers.ollama import OllamaManager, OllamaNotReadyError
from ai_runtime.storage.data_home import get_elfie_home
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
AUTHORITY_START_TIMEOUT_SECONDS = 30.0


def _supervisor_for(command: Sequence[str], http_port: int) -> RuntimeSupervisor:
    """Build the one Runtime Supervisor used by source and installed CLI commands."""
    launch_command = tuple(command)
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
            get_elfie_home(),
            PROJECT_ROOT,
            command=launch_command,
            health_checker=healthy,
            timeout_seconds=BACKGROUND_START_TIMEOUT_SECONDS,
            child_environment={"ELFIENEST_GODOT_NONCE": generation_nonce},
        )

    return RuntimeSupervisor(
        elfie_home=get_elfie_home(),
        project_root=PROJECT_ROOT,
        health_probe=lambda: _full_runtime_health(http_port),
        start_core=start_core,
        stop_core=lambda: stop_service(get_elfie_home(), PROJECT_ROOT),
        prepare_optional_component=_start_configured_public_ollama,
        owns_pid_record=lambda: (get_elfie_home() / PID_FILENAME).is_file(),
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
    *,
    owner_id: str = "cli",
) -> ServiceLifecycleResult:
    """Start the service once; a verified running process is left untouched."""
    launch_command = (
        tuple(command) if command is not None else default_service_command(("--lan",))
    )
    try:
        http_port = _validated_http_port(launch_command)
    except ValueError as error:
        result = ServiceLifecycleResult(
            status="failed", error=LaunchFailedError(f"服务端口参数无效: {error}")
        )
        _print_start_result(result)
        return result
    result = _supervisor_for(launch_command, http_port).start(owner_id=owner_id)
    _print_start_result(result)
    return result


def stop_background_service(owner_id: str = "cli") -> ServiceLifecycleResult:
    """Stop only the current project's verified service process."""
    supervisor = _supervisor_for(default_service_command(), DEFAULT_HTTP_PORT)
    if owner_id != "cli":
        health = supervisor.status()
        if health.owner_lease is not None and health.owner_lease.owner_id != owner_id:
            result = ServiceLifecycleResult(
                status="failed",
                error=LaunchFailedError("Runtime owner lease 不允许当前客户端停止服务"),
            )
            print(f"  ❌ 服务停止失败: {result.error}")
            return result
    result = supervisor.stop()
    if result.status == "stopped":
        print("  ✅ 服务已停止")
    elif result.status == "already_stopped":
        print("  ⭕ 服务未运行")
    else:
        print(f"  ❌ 服务停止失败: {result.error}")
    return result


def restart_background_service() -> ServiceLifecycleResult:
    """Stop the current process and start it again with its existing arguments."""
    stopped = _supervisor_for(default_service_command(), DEFAULT_HTTP_PORT).stop()
    if stopped.status == "failed":
        print(f"  ❌ 无法重启服务: {stopped.error}")
        return stopped
    command = stopped.command or default_service_command(("--lan",))
    try:
        http_port = _validated_http_port(command)
    except ValueError as error:
        result = ServiceLifecycleResult(
            status="failed", error=LaunchFailedError(f"服务端口参数无效: {error}")
        )
        print(f"  ❌ 服务重启失败: {result.error}")
        return result
    launch_command = tuple(argument for argument in command if argument != "--force")
    result = _supervisor_for(launch_command, http_port).start(owner_id="cli")
    if result.status in {"started", "already_running"}:
        print("  ✅ 服务已重启")
    else:
        print(f"  ❌ 服务重启失败: {result.error}")
    return result


def show_service_status(*, json_output: bool = False) -> None:
    """Print lifecycle state without duplicating usage/session statistics."""
    inspector = DefaultProcessInspector()
    elfie_home = get_elfie_home()
    running = existing_service_command(elfie_home, PROJECT_ROOT, inspector)
    status_command = running[1] if running is not None else default_service_command()
    status_port = http_port_from_command(status_command)
    health = _supervisor_for(status_command, status_port).status()
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
    print("  📊 服务状态")
    print("  " + "=" * 45)
    print()
    if running is None:
        port_statuses = default_port_statuses()
        external = _external_recorded_service(elfie_home, inspector)
        if external is not None:
            pid, cwd, _ = external
            print(f"  ⚠️  已登记 PID {pid} 来自其他 ElfieNest checkout: {cwd}")
        elif any(port_status.running for port_status in port_statuses):
            print("  ⚠️  默认服务端口被外部进程占用，当前项目没有可验证服务。")
    else:
        _, command = running
        ports = service_ports_from_command(command)
        port_statuses = service_port_statuses(ports[0], ports[2], ports[1])
    for port_status in port_statuses:
        is_current_project = running is not None
        state = (
            "运行中"
            if is_current_project and port_status.running
            else "被外部进程占用"
            if port_status.running
            else "未运行"
        )
        icon = (
            "✅"
            if is_current_project and port_status.running
            else "⚠️"
            if port_status.running
            else "⭕"
        )
        print(f"  {icon} {port_status.name}: {state} (端口 {port_status.port})")
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
                error=LaunchFailedError(f"已登记服务但 Web 端口 {port} 未通过健康检查"),
            )
            print(f"  ❌ 无法打开 Web 管理台: {result.error}")
            return result
    else:
        if _web_is_healthy(8000):
            webbrowser.open(WEB_URL)
            print(f"  🌐 已打开已运行的 Web 管理台: {WEB_URL}")
            print("  ⚠️  该服务未由当前项目 PID 收据验证；start/restart 不会接管它。")
            return ServiceLifecycleResult(status="already_running")
        if any(port_status.running for port_status in default_port_statuses()):
            result = ServiceLifecycleResult(
                status="failed",
                error=LaunchFailedError(
                    "默认服务端口已被外部进程占用，且 Web 健康检查未通过；"
                    "请从占用服务所属 checkout 管理它，或使用自定义端口启动当前项目"
                ),
            )
            print(f"  ❌ 无法打开 Web 管理台: {result.error}")
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
                error=LaunchFailedError(f"服务已启动但 Web 端口 {port} 未通过健康检查"),
            )
            print(f"  ❌ 无法打开 Web 管理台: {result.error}")
            return result
    web_url = f"http://127.0.0.1:{port}/"
    webbrowser.open(web_url)
    print(f"  🌐 已打开 Web 管理台: {web_url}")
    return ServiceLifecycleResult(status="already_running")


def start_desktop_application() -> ServiceLifecycleResult:
    """Explicitly start the packaged Electron Desktop supervisor."""
    result = desktop_lifecycle.start_desktop_application(
        get_elfie_home(), PROJECT_ROOT, health_checker=_web_is_healthy
    )
    if result.status in {"started", "already_running"}:
        print(f"  ✅ Desktop 已启动 (PID {result.pid})")
    else:
        print(f"  ❌ Desktop 启动失败: {result.error}")
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
        print(f"  ✅ 服务已启动 (PID {result.pid})")
    elif result.status == "already_running":
        print(f"  ⭕ 服务已在运行 (PID {result.pid})")
    else:
        print(f"  ❌ 服务启动失败: {result.error}")
